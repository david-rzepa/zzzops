#!/usr/bin/env bash
set -u

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
TARGET_SKILLS=(add-zzzops-goal execute-zzzops migrate-to-zzzops suggest-zzzops-work)
DRY_RUN=0
OVERWRITE=0

fail() { printf 'Cannot install yet: %s\n' "$1"; exit 2; }

[[ $# -ge 1 ]] || fail 'Usage: install.sh TARGET [--dry-run] [--overwrite-mechanical]'
TARGET_INPUT=$1
shift
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1 ;;
        --overwrite-mechanical) OVERWRITE=1 ;;
        *) fail "Unknown option: $1" ;;
    esac
    shift
done
TARGET_ROOT="$(cd "$TARGET_INPUT" 2>/dev/null && pwd -P)" || fail 'Target is not a directory'
[[ -e "$TARGET_ROOT/.git" ]] || fail 'Target has no .git entry'

PAIR_SOURCE=()
PAIR_RELATIVE=()
add_pair() { PAIR_SOURCE+=("$1"); PAIR_RELATIVE+=("$2"); }

build_pairs() {
    PAIR_SOURCE=(); PAIR_RELATIVE=()
    local relative root file name suffix
    local fixed=(
        .zzzops/rules/BACKENDS.md .zzzops/rules/BLOCKERS.md .zzzops/rules/CONTINUATION.md
        .zzzops/rules/EXECUTION_STRATEGY.md .zzzops/rules/GOAL_SYSTEM.md .zzzops/rules/INITIALIZATION.md
        .agents/.gitignore .agents/zzzops.py
    )
    for relative in "${fixed[@]}"; do add_pair "$SOURCE_ROOT/$relative" "$relative"; done
    local roots=("$SOURCE_ROOT/.agents/templates/project-goals")
    for name in "${TARGET_SKILLS[@]}"; do roots+=("$SOURCE_ROOT/.agents/skills/$name"); done
    for root in "${roots[@]}"; do
        while IFS= read -r -d '' file; do
            [[ "$file" == */__pycache__/* || "${file##*/}" == test_* ]] && continue
            relative=${file#"$SOURCE_ROOT/"}
            add_pair "$file" "$relative"
        done < <(find "$root" -type f -print0)
    done
    for name in "${TARGET_SKILLS[@]}"; do
        root="$SOURCE_ROOT/.agents/skills/$name"
        while IFS= read -r -d '' file; do
            [[ "$file" == */__pycache__/* || "${file##*/}" == test_* ]] && continue
            suffix=${file#"$root/"}
            add_pair "$file" ".claude/skills/$name/$suffix"
        done < <(find "$root" -type f -print0)
    done
    add_pair "$SOURCE_ROOT/.agents/.gitignore" '.claude/.gitignore'
    add_pair "$SOURCE_ROOT/.agents/templates/project-goals/ZZZOPS_GITIGNORE" '.zzzops/.gitignore'
}

file_digest() {
    [[ -f "$1" ]] || return 0
    git hash-object --no-filters -- "$1" 2>/dev/null
}

has_unsafe_symlink() {
    local relative=$1 current=$TARGET_ROOT part
    local old_ifs=$IFS
    IFS='/' read -r -a parts <<< "$relative"
    IFS=$old_ifs
    for part in "${parts[@]}"; do
        current="$current/$part"
        [[ -L "$current" ]] && return 0
    done
    return 1
}

IGNORED=()
IGNORE_WARNING=''
probe_ignored_roots() {
    IGNORED=(); IGNORE_WARNING=''
    local root probe code
    local roots=(.agents .claude)
    for root in "${roots[@]}"; do
        local probes=()
        if [[ "$root" == .agents ]]; then probes=(.agents/zzzops.py .agents/skills/execute-zzzops/SKILL.md)
        else probes=(.claude/skills/execute-zzzops/SKILL.md)
        fi
        for probe in "${probes[@]}"; do
            git -c "safe.directory=$TARGET_ROOT" -C "$TARGET_ROOT" check-ignore --no-index --quiet -- "$probe" >/dev/null 2>&1
            code=$?
            if [[ $code -eq 0 ]]; then IGNORED+=("$root"); break; fi
            if [[ $code -ne 1 ]]; then
                IGNORE_WARNING='Could not verify project mechanic ignore rules with Git.'
                return
            fi
        done
    done
}

PLAN_RELATIVE=()
PLAN_SOURCE=()
PLAN_DESTINATION=()
PLAN_ACTION=()
PLAN_EXPECTED=()
PLAN_SOURCE_HASH=()
PLAN_ERRORS=()
PLAN_SIGNATURE=''

build_plan() {
    build_pairs
    PLAN_RELATIVE=(); PLAN_SOURCE=(); PLAN_DESTINATION=(); PLAN_ACTION=(); PLAN_EXPECTED=(); PLAN_SOURCE_HASH=(); PLAN_ERRORS=()
    local i relative source destination source_hash expected action
    for ((i=0; i<${#PAIR_SOURCE[@]}; i++)); do
        source=${PAIR_SOURCE[$i]}; relative=${PAIR_RELATIVE[$i]}; destination="$TARGET_ROOT/$relative"
        if has_unsafe_symlink "$relative"; then
            PLAN_ERRORS+=("A managed path uses a symlink: $relative")
            continue
        fi
        source_hash=$(file_digest "$source")
        expected=$(file_digest "$destination")
        if [[ -d "$destination" ]]; then
            action=conflict
            PLAN_ERRORS+=("ZzzOps manages $relative as a file, but the target contains a directory there.")
        elif [[ -z "$expected" ]]; then action=create
        elif [[ "$expected" == "$source_hash" ]]; then action=unchanged
        elif [[ $OVERWRITE -eq 1 ]]; then action=overwrite
        else
            action=conflict
            PLAN_ERRORS+=("ZzzOps already manages $relative, but its contents differ. Review it before using --overwrite-mechanical.")
        fi
        PLAN_RELATIVE+=("$relative"); PLAN_SOURCE+=("$source"); PLAN_DESTINATION+=("$destination")
        PLAN_ACTION+=("$action"); PLAN_EXPECTED+=("$expected"); PLAN_SOURCE_HASH+=("$source_hash")
    done
    probe_ignored_roots
    PLAN_SIGNATURE=$(
        for ((i=0; i<${#PLAN_RELATIVE[@]}; i++)); do
            printf '%s|%s|%s|%s\n' "${PLAN_RELATIVE[$i]}" "${PLAN_ACTION[$i]}" "${PLAN_SOURCE_HASH[$i]}" "${PLAN_EXPECTED[$i]}"
        done
        printf 'ignored|%s\nwarning|%s\n' "${IGNORED[*]}" "$IGNORE_WARNING"
    )
}

show_preview() {
    printf 'ZzzOps installation preview\nTarget: %s\n' "$TARGET_ROOT"
    printf '%s\n' 'This will install:' '- tracked project skills for Codex and Claude Code' '- shared workflow rules and the ZzzOps control CLI' '- blank templates for project setup and TODO migration'
    local new_count=0 updated_count=0 action error names=''
    for action in "${PLAN_ACTION[@]}"; do
        [[ "$action" == create ]] && ((new_count+=1))
        [[ "$action" == overwrite ]] && ((updated_count+=1))
    done
    if [[ $new_count -gt 0 || $updated_count -gt 0 ]]; then printf 'Planned changes: %d new, %d updated.\n' "$new_count" "$updated_count"
    else printf 'Planned changes: ZzzOps is already up to date.\n'; fi
    if [[ ${#IGNORED[@]} -gt 0 ]]; then
        for action in "${IGNORED[@]}"; do
            [[ -n "$names" ]] && names+=' and '
            names+="$action/"
        done
        printf 'Warning: Git ignores required ZzzOps project mechanics under %s.\n' "$names"
        printf 'Remove those ignore rules before committing so collaborators receive the installed workflows.\n'
    fi
    [[ -n "$IGNORE_WARNING" ]] && printf 'Warning: %s\n' "$IGNORE_WARNING"
    for error in "${PLAN_ERRORS[@]}"; do printf 'Cannot install yet: %s\n' "$error"; done
}

WRITTEN_RELATIVE=()
WRITTEN_HAD_BEFORE=()
BACKUP_ROOT=''
rollback() {
    local i relative destination backup
    for ((i=0; i<${#WRITTEN_RELATIVE[@]}; i++)); do
        relative=${WRITTEN_RELATIVE[$i]}; destination="$TARGET_ROOT/$relative"; backup="$BACKUP_ROOT/$relative"
        rm -f "$destination"
        if [[ "${WRITTEN_HAD_BEFORE[$i]}" == 1 ]]; then
            mkdir -p "$(dirname "$destination")"
            cp -p "$backup" "$destination"
        fi
    done
}

apply_plan() {
    BACKUP_ROOT=$(mktemp -d "${TMPDIR:-/tmp}/zzzops-install.XXXXXX") || return 1
    WRITTEN_RELATIVE=(); WRITTEN_HAD_BEFORE=()
    local i action relative source destination current backup temporary
    for ((i=0; i<${#PLAN_RELATIVE[@]}; i++)); do
        action=${PLAN_ACTION[$i]}
        [[ "$action" == create || "$action" == overwrite ]] || continue
        relative=${PLAN_RELATIVE[$i]}; source=${PLAN_SOURCE[$i]}; destination=${PLAN_DESTINATION[$i]}
        current=$(file_digest "$destination")
        if [[ "$current" != "${PLAN_EXPECTED[$i]}" ]]; then rollback; rm -rf "$BACKUP_ROOT"; return 1; fi
        backup="$BACKUP_ROOT/$relative"
        if [[ -f "$destination" ]]; then
            mkdir -p "$(dirname "$backup")"
            cp -p "$destination" "$backup" || { rollback; rm -rf "$BACKUP_ROOT"; return 1; }
            WRITTEN_HAD_BEFORE+=(1)
        else WRITTEN_HAD_BEFORE+=(0); fi
        WRITTEN_RELATIVE+=("$relative")
        mkdir -p "$(dirname "$destination")" || { rollback; rm -rf "$BACKUP_ROOT"; return 1; }
        temporary="$(dirname "$destination")/.zzzops-install.$$.$i.tmp"
        cp "$source" "$temporary" && mv -f "$temporary" "$destination" || {
            rm -f "$temporary"; rollback; rm -rf "$BACKUP_ROOT"; return 1;
        }
    done
    rm -rf "$BACKUP_ROOT"
    return 0
}

build_plan
show_preview
[[ ${#PLAN_ERRORS[@]} -eq 0 ]] || exit 2
if [[ $DRY_RUN -eq 1 ]]; then printf 'No files were changed.\n'; exit 0; fi
printf 'Install these changes? [y/N] '
IFS= read -r answer || answer=''
answer=${answer%$'\r'}
case "$answer" in y|Y|yes|YES|Yes) ;; *) printf 'Installation cancelled; no files were changed.\n'; exit 0 ;; esac
preview_signature=$PLAN_SIGNATURE
build_plan
if [[ ${#PLAN_ERRORS[@]} -gt 0 || "$PLAN_SIGNATURE" != "$preview_signature" ]]; then
    printf 'The target changed after the preview. Run the installer again; no files were changed.\n'
    exit 2
fi
if ! apply_plan; then printf 'Installation failed and was rolled back.\n'; exit 2; fi
printf 'ZzzOps is installed. Start any ZzzOps workflow to set up the project.\n'
