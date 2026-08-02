#!/usr/bin/env bash
set -u

SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
TARGET_SKILLS=(add-zzzops-goal execute-zzzops migrate-to-zzzops review-zzzops-policy send-zzzops-feedback suggest-zzzops-work)
INSTALL_MANIFEST_RELATIVE='.agents/zzzops/INSTALL_MANIFEST'
DRY_RUN=0
OVERWRITE=0
ASSUME_YES=0

fail() { printf 'Cannot install yet: %s\n' "$1"; exit 2; }

[[ $# -ge 1 ]] || fail 'Usage: install.sh TARGET [--dry-run] [--overwrite-mechanical] [--yes]'
TARGET_INPUT=$1
shift
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=1 ;;
        --overwrite-mechanical) OVERWRITE=1 ;;
        --yes) ASSUME_YES=1 ;;
        *) fail "Unknown option: $1" ;;
    esac
    shift
done
TARGET_ROOT="$(cd "$TARGET_INPUT" 2>/dev/null && pwd -P)" || fail 'Target is not a directory'
[[ -e "$TARGET_ROOT/.git" ]] || fail 'Target has no .git entry'
SOURCE_REVISION=$(git -C "$SOURCE_ROOT" rev-parse HEAD 2>/dev/null) || fail 'Source revision could not be read from the ZzzOps base repository'
[[ "$SOURCE_REVISION" =~ ^[0-9a-f]{40,64}$ ]] || fail 'Source revision is invalid'
SOURCE_VERSION=$(git -c core.excludesFile=/dev/null -C "$SOURCE_ROOT" describe --tags --always --long --dirty 2>/dev/null) || fail 'Source version could not be read from the ZzzOps base repository'
[[ "$SOURCE_VERSION" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$ ]] || fail 'Source version is invalid'

PAIR_SOURCE=()
PAIR_RELATIVE=()
add_pair() { PAIR_SOURCE+=("$1"); PAIR_RELATIVE+=("$2"); }

build_pairs() {
    PAIR_SOURCE=(); PAIR_RELATIVE=()
    local relative root file name suffix
    local fixed=(
        .zzzops/rules/BACKENDS.md .zzzops/rules/BLOCKERS.md .zzzops/rules/CONTINUATION.md
        .zzzops/rules/EXECUTION_STRATEGY.md .zzzops/rules/FEEDBACK.md .zzzops/rules/GOAL_SYSTEM.md .zzzops/rules/INITIALIZATION.md
        .agents/zzzops/zzzops.py .agents/zzzops/policy.py .agents/zzzops/reservation.py .agents/zzzops/feedback.py .agents/zzzops/goals.py .agents/zzzops/portfolio.py .agents/zzzops/install_lock.py LICENSE
    )
    for relative in "${fixed[@]}"; do
        [[ "$relative" == LICENSE ]] && add_pair "$SOURCE_ROOT/$relative" '.agents/zzzops/LICENSE' || add_pair "$SOURCE_ROOT/$relative" "$relative"
    done
    add_pair "$SOURCE_ROOT/.agents/.gitignore" '.agents/zzzops/.gitignore'
    local roots=("$SOURCE_ROOT/.agents/zzzops/templates/project-goals")
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
    add_pair "$SOURCE_ROOT/.agents/zzzops/templates/project-goals/ZZZOPS_GITIGNORE" '.zzzops/.gitignore'
}

file_digest() {
    [[ -f "$1" ]] || return 0
    git hash-object --no-filters -- "$1" 2>/dev/null
}

MANIFEST_EXISTS=0
MANIFEST_VALID=1
MANIFEST_REVISION=''
MANIFEST_VERSION=''
MANIFEST_RELATIVE=()
MANIFEST_HASH=()
read_manifest() {
    MANIFEST_EXISTS=0; MANIFEST_VALID=1; MANIFEST_REVISION=''; MANIFEST_VERSION=''; MANIFEST_RELATIVE=(); MANIFEST_HASH=()
    local path="$TARGET_ROOT/$INSTALL_MANIFEST_RELATIVE" line kind hash relative first=1
    [[ -f "$path" ]] || return
    MANIFEST_EXISTS=1
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ $first -eq 1 ]]; then
            [[ "$line" == zzzops-install-manifest-v1 ]] || MANIFEST_VALID=0
            first=0
            continue
        fi
        IFS=$'\t' read -r kind hash relative <<< "$line"
        if [[ "$kind" == revision && "$hash" =~ ^[0-9a-f]{40,64}$ && -z "$relative" && -z "$MANIFEST_REVISION" ]]; then
            MANIFEST_REVISION=$hash
        elif [[ "$kind" == version && "$hash" =~ ^[A-Za-z0-9][A-Za-z0-9._+-]{0,127}$ && -z "$relative" && -z "$MANIFEST_VERSION" ]]; then
            MANIFEST_VERSION=$hash
        elif [[ "$kind" == file && "$hash" =~ ^[0-9a-f]{40,64}$ && -n "$relative" ]]; then
            for existing in "${MANIFEST_RELATIVE[@]:-}"; do
                [[ -n "$existing" && "$existing" == "$relative" ]] && MANIFEST_VALID=0
            done
            MANIFEST_HASH+=("$hash"); MANIFEST_RELATIVE+=("$relative")
        else MANIFEST_VALID=0
        fi
    done < "$path"
    [[ -n "$MANIFEST_REVISION" ]] || MANIFEST_VALID=0
}

manifest_hash_for() {
    local wanted=$1 i
    for ((i=0; ; i++)); do
        [[ -n "${MANIFEST_RELATIVE[$i]:-}" ]] || return
        [[ "${MANIFEST_RELATIVE[$i]}" == "$wanted" ]] && { printf '%s' "${MANIFEST_HASH[$i]}"; return; }
    done
}

write_manifest_content() {
    local i
    printf 'zzzops-install-manifest-v1\nrevision\t%s\nversion\t%s\n' "$SOURCE_REVISION" "$SOURCE_VERSION"
    for ((i=0; i<${#PLAN_RELATIVE[@]}; i++)); do
        printf 'file\t%s\t%s\n' "${PLAN_SOURCE_HASH[$i]}" "${PLAN_RELATIVE[$i]}"
    done
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
        if [[ "$root" == .agents ]]; then probes=(.agents/zzzops/zzzops.py .agents/skills/execute-zzzops/SKILL.md)
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
PLAN_MANIFEST_EXPECTED=''
PLAN_MANIFEST_NEEDS_UPDATE=0
PLAN_IS_UPGRADE=0

build_plan() {
    build_pairs
    PLAN_RELATIVE=(); PLAN_SOURCE=(); PLAN_DESTINATION=(); PLAN_ACTION=(); PLAN_EXPECTED=(); PLAN_SOURCE_HASH=(); PLAN_ERRORS=()
    PLAN_IS_UPGRADE=0; PLAN_MANIFEST_NEEDS_UPDATE=0
    read_manifest
    [[ $MANIFEST_EXISTS -eq 0 || $MANIFEST_VALID -eq 1 || $OVERWRITE -eq 1 ]] || PLAN_ERRORS+=("The installed ZzzOps manifest is invalid. Review $INSTALL_MANIFEST_RELATIVE before using --overwrite-mechanical.")
    local i relative source destination source_hash expected installed action
    for ((i=0; i<${#PAIR_SOURCE[@]}; i++)); do
        source=${PAIR_SOURCE[$i]}; relative=${PAIR_RELATIVE[$i]}; destination="$TARGET_ROOT/$relative"
        if has_unsafe_symlink "$relative"; then
            PLAN_ERRORS+=("A managed path uses a symlink: $relative")
            continue
        fi
        source_hash=$(file_digest "$source")
        expected=$(file_digest "$destination")
        installed=$(manifest_hash_for "$relative")
        if [[ -d "$destination" ]]; then
            action=conflict
            PLAN_ERRORS+=("ZzzOps manages $relative as a file, but the target contains a directory there.")
        elif [[ $MANIFEST_EXISTS -eq 0 && -z "$expected" ]]; then action=create
        elif [[ $MANIFEST_EXISTS -eq 0 && "$expected" == "$source_hash" ]]; then action=unchanged
        elif [[ $MANIFEST_EXISTS -eq 0 && $OVERWRITE -eq 1 ]]; then action=overwrite
        elif [[ $MANIFEST_EXISTS -eq 0 ]]; then
            action=conflict
            PLAN_ERRORS+=("ZzzOps already manages $relative, but no installed baseline proves it is safe to upgrade. Review it before using --overwrite-mechanical.")
        elif [[ $MANIFEST_VALID -ne 1 ]]; then
            if [[ $OVERWRITE -eq 1 ]]; then [[ -z "$expected" ]] && action=create || action=overwrite
            else action=conflict; fi
        elif [[ -z "$installed" && -z "$expected" ]]; then action=create; PLAN_IS_UPGRADE=1
        elif [[ -z "$installed" || "$expected" != "$installed" ]]; then
            if [[ $OVERWRITE -eq 1 ]]; then action=overwrite
            else
                action=conflict
                PLAN_ERRORS+=("ZzzOps-managed file $relative is locally divergent from its installed baseline. Review it before using --overwrite-mechanical.")
            fi
        elif [[ "$expected" == "$source_hash" ]]; then action=unchanged
        else action=upgrade; PLAN_IS_UPGRADE=1
        fi
        PLAN_RELATIVE+=("$relative"); PLAN_SOURCE+=("$source"); PLAN_DESTINATION+=("$destination")
        PLAN_ACTION+=("$action"); PLAN_EXPECTED+=("$expected"); PLAN_SOURCE_HASH+=("$source_hash")
    done
    probe_ignored_roots
    if [[ $MANIFEST_EXISTS -eq 1 && $MANIFEST_VALID -eq 1 && ( "$MANIFEST_REVISION" != "$SOURCE_REVISION" || "$MANIFEST_VERSION" != "$SOURCE_VERSION" ) ]]; then
        PLAN_MANIFEST_NEEDS_UPDATE=1
        PLAN_IS_UPGRADE=1
    fi
    PLAN_MANIFEST_EXPECTED=$(file_digest "$TARGET_ROOT/$INSTALL_MANIFEST_RELATIVE")
    PLAN_SIGNATURE=$(
        for ((i=0; i<${#PLAN_RELATIVE[@]}; i++)); do
            printf '%s|%s|%s|%s\n' "${PLAN_RELATIVE[$i]}" "${PLAN_ACTION[$i]}" "${PLAN_SOURCE_HASH[$i]}" "${PLAN_EXPECTED[$i]}"
        done
        printf 'manifest|%s|%s|%s|%s|%s\nignored|%s\nwarning|%s\n' "$PLAN_MANIFEST_EXPECTED" "$MANIFEST_REVISION" "$MANIFEST_VERSION" "$SOURCE_REVISION" "$SOURCE_VERSION" "${IGNORED[*]:-}" "$IGNORE_WARNING"
    )
}

show_preview() {
    printf 'ZzzOps installation preview\nTarget: %s\n' "$TARGET_ROOT"
    printf '%s\n' 'This will install:' '- tracked project skills for Codex and Claude Code' '- shared workflow rules and the ZzzOps control CLI' '- blank templates for project setup and TODO migration'
    local installed_display source_display="$SOURCE_VERSION (${SOURCE_REVISION:0:7})"
    if [[ $MANIFEST_EXISTS -eq 0 ]]; then installed_display='not installed'
    elif [[ -n "$MANIFEST_VERSION" ]]; then installed_display="$MANIFEST_VERSION (${MANIFEST_REVISION:0:7})"
    else installed_display="revision ${MANIFEST_REVISION:0:7}"; fi
    printf 'ZzzOps version: %s -> %s.\n' "$installed_display" "$source_display"
    local new_count=0 updated_count=0 action error names='' i subjects
    for action in "${PLAN_ACTION[@]}"; do
        [[ "$action" == create ]] && ((new_count+=1))
        [[ "$action" == upgrade || "$action" == overwrite ]] && ((updated_count+=1))
    done
    if [[ $PLAN_IS_UPGRADE -eq 1 ]]; then
        printf 'Upgrade available: %.7s -> %.7s.\nManaged files to update:\n' "$MANIFEST_REVISION" "$SOURCE_REVISION"
        for ((i=0; i<${#PLAN_ACTION[@]}; i++)); do
            [[ "${PLAN_ACTION[$i]}" == create || "${PLAN_ACTION[$i]}" == upgrade ]] && printf -- '- %s\n' "${PLAN_RELATIVE[$i]}"
        done
        printf 'Changes since installed version:\n'
        subjects=$(git -C "$SOURCE_ROOT" log --no-merges --format='- %s' --max-count=8 "$MANIFEST_REVISION..$SOURCE_REVISION" 2>/dev/null) || subjects=''
        [[ -n "$subjects" ]] && printf '%s\n' "$subjects" || printf '%s\n' '- revision history is unavailable; inspect the managed-file list above'
    elif [[ $new_count -gt 0 || $updated_count -gt 0 ]]; then printf 'Planned changes: %d new, %d updated.\n' "$new_count" "$updated_count"
    elif [[ -z "${PLAN_ERRORS[*]:-}" ]]; then printf 'Planned changes: ZzzOps is already up to date.\n'; fi
    if [[ -n "${IGNORED[*]:-}" ]]; then
        for action in "${IGNORED[@]:-}"; do
            [[ -n "$action" ]] || continue
            [[ -n "$names" ]] && names+=' and '
            names+="$action/"
        done
        printf 'Warning: Git ignores required ZzzOps project mechanics under %s.\n' "$names"
        printf 'Remove those ignore rules before committing so collaborators receive the installed workflows.\n'
    fi
    [[ -n "$IGNORE_WARNING" ]] && printf 'Warning: %s\n' "$IGNORE_WARNING"
    for error in "${PLAN_ERRORS[@]:-}"; do
        [[ -n "$error" ]] && printf 'Cannot install yet: %s\n' "$error"
    done
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
    current=$(file_digest "$TARGET_ROOT/$INSTALL_MANIFEST_RELATIVE")
    [[ "$current" == "$PLAN_MANIFEST_EXPECTED" ]] || { rm -rf "$BACKUP_ROOT"; return 1; }
    for ((i=0; i<${#PLAN_RELATIVE[@]}; i++)); do
        action=${PLAN_ACTION[$i]}
        [[ "$action" == create || "$action" == upgrade || "$action" == overwrite ]] || continue
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
    relative=$INSTALL_MANIFEST_RELATIVE; destination="$TARGET_ROOT/$relative"; backup="$BACKUP_ROOT/$relative"
    current=$(file_digest "$destination")
    if [[ "$current" != "$PLAN_MANIFEST_EXPECTED" ]]; then rollback; rm -rf "$BACKUP_ROOT"; return 1; fi
    if [[ -f "$destination" ]]; then
        mkdir -p "$(dirname "$backup")"
        cp -p "$destination" "$backup" || { rollback; rm -rf "$BACKUP_ROOT"; return 1; }
        WRITTEN_HAD_BEFORE+=(1)
    else WRITTEN_HAD_BEFORE+=(0); fi
    WRITTEN_RELATIVE+=("$relative")
    mkdir -p "$(dirname "$destination")" || { rollback; rm -rf "$BACKUP_ROOT"; return 1; }
    temporary="$(dirname "$destination")/.zzzops-install.$$-manifest.tmp"
    write_manifest_content > "$temporary" && mv -f "$temporary" "$destination" || {
        rm -f "$temporary"; rollback; rm -rf "$BACKUP_ROOT"; return 1;
    }
    rm -rf "$BACKUP_ROOT"
    return 0
}

build_plan
show_preview
[[ -z "${PLAN_ERRORS[*]:-}" ]] || exit 2
if [[ $DRY_RUN -eq 1 ]]; then printf 'No files were changed.\n'; exit 0; fi
pending_changes=0
for action in "${PLAN_ACTION[@]}"; do
    [[ "$action" == create || "$action" == upgrade || "$action" == overwrite ]] && ((pending_changes+=1))
done
((pending_changes+=PLAN_MANIFEST_NEEDS_UPDATE))
if [[ $pending_changes -eq 0 ]]; then
    printf 'ZzzOps is already up to date. No further action is necessary.\n'
    exit 0
fi
if [[ $ASSUME_YES -eq 0 ]]; then
    if [[ $PLAN_IS_UPGRADE -eq 1 ]]; then printf 'Upgrade ZzzOps? [y/N] '
    else printf 'Install these changes? [y/N] '; fi
    IFS= read -r answer || answer=''
    answer=${answer%$'\r'}
    case "$answer" in y|Y|yes|YES|Yes) ;; *) printf 'Installation cancelled; no files were changed.\n'; exit 0 ;; esac
fi
preview_signature=$PLAN_SIGNATURE
build_plan
if [[ -n "${PLAN_ERRORS[*]:-}" || "$PLAN_SIGNATURE" != "$preview_signature" ]]; then
    printf 'The target changed after the preview. Run the installer again; no files were changed.\n'
    exit 2
fi
if ! apply_plan; then printf 'Installation failed and was rolled back.\n'; exit 2; fi
if [[ $PLAN_IS_UPGRADE -eq 1 ]]; then printf 'ZzzOps was upgraded.\n'
else printf 'ZzzOps is installed. Open the target repository in Codex or Claude Code; restart or reopen the harness if the new skills are not discovered. Begin with review-zzzops-policy.\n'; fi
