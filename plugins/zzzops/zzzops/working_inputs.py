"""Durable local working inputs and exact provider-dispatch snapshots."""
from __future__ import annotations

from contextlib import contextmanager
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import threading
import uuid

try:
    import fcntl
except ImportError:  # Windows
    fcntl = None
    import msvcrt


_ACTIVE_LOCK = threading.RLock()
_ACTIVE: dict[tuple[str, str], dict[str, int]] = {}
_LOCAL_LOCKS: dict[str, threading.RLock] = {}


def _atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        handle.flush(); os.fsync(handle.fileno())
    os.replace(temporary, path)
    try:
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    except OSError:  # Directory handles cannot be flushed on Windows.
        pass


class WorkingInputBusy(RuntimeError):
    def __init__(self, message: str, recovery: dict):
        super().__init__(message); self.recovery = recovery


class WorkingInputUncertain(RuntimeError):
    def __init__(self, message: str, recovery: dict):
        super().__init__(message); self.recovery = recovery


class WorkingInputStore:
    def __init__(self, repo: Path, *, repository: str, owner: str,
                 provider_check=None, fault=None):
        self.repo = Path(repo).resolve()
        self.repository = repository
        self.owner = owner
        self.provider_check = provider_check or (lambda request_id, digest: None)
        self.fault = fault or (lambda point: None)
        self.root = self.repo / ".zzzops/work/inputs/v1"
        self.index_path = self.root / "index.json"
        self.lock_path = self.root / ".lock"
        self.root.mkdir(parents=True, exist_ok=True)
        self._install_ignore()

    def _install_ignore(self):
        info = self.repo / ".git/info/exclude"
        if not info.parent.exists(): return
        marker = ".zzzops/work/inputs/"
        text = info.read_text(encoding="utf-8") if info.exists() else ""
        if marker not in text.splitlines():
            info.parent.mkdir(parents=True, exist_ok=True)
            with info.open("a", encoding="utf-8") as handle:
                if text and not text.endswith("\n"): handle.write("\n")
                handle.write(marker + "\n")

    @contextmanager
    def _locked(self):
        self.lock_path.touch(exist_ok=True)
        local = _LOCAL_LOCKS.setdefault(str(self.lock_path), threading.RLock())
        with local, self.lock_path.open("r+b") as handle:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            else:
                if not handle.read(1):
                    handle.write(b"0"); handle.flush()
                handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                else:
                    handle.seek(0); msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

    def _load(self):
        try: return json.loads(self.index_path.read_text(encoding="utf-8"))
        except FileNotFoundError: return {"inputs": {}, "requests": {}}

    def _save(self, state): _atomic_json(self.index_path, state)

    def _key(self, subject, purpose, owner=None):
        return "\0".join((owner or self.owner, purpose, subject))

    def _descriptor(self, record):
        return {key: record[key] for key in ("payload_id", "path", "subject", "purpose", "owner")}

    def open(self, subject, purpose, create=True):
        with self._locked():
            state = self._load(); key = self._key(subject, purpose)
            payload_id = state["inputs"].get(key)
            if payload_id is None:
                if not create: raise KeyError((subject, purpose))
                payload_id = hashlib.sha256((self.repository + "\0" + key).encode()).hexdigest()[:32]
                path = self.root / payload_id / "input.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{}", encoding="utf-8")
                record = {"payload_id": payload_id, "path": str(path), "subject": subject,
                          "purpose": purpose, "owner": self.owner}
                state["inputs"][key] = payload_id; state[payload_id] = record; self._save(state)
            return self._descriptor(state[payload_id])

    def write(self, subject, purpose, value):
        descriptor = self.open(subject, purpose)
        data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        with self._locked():
            path = Path(descriptor["path"])
            with path.open("r+b") as handle:
                handle.seek(0); handle.write(data); handle.truncate(); handle.flush(); os.fsync(handle.fileno())
        return descriptor

    def read(self, subject, purpose):
        descriptor = self.open(subject, purpose, create=False)
        return json.loads(Path(descriptor["path"]).read_text(encoding="utf-8"))

    def relabel(self, old_subject, new_subject, purpose):
        with self._locked():
            state = self._load(); old = self._key(old_subject, purpose)
            if old not in state["inputs"]: raise KeyError(old_subject)
            payload_id = state["inputs"].pop(old); record = state[payload_id]
            record.update(subject=new_subject)
            state["inputs"][self._key(new_subject, purpose, record["owner"])] = payload_id
            self._save(state); return self._descriptor(record)

    def handoff(self, subject, purpose, owner):
        with self._locked():
            state = self._load(); key = self._key(subject, purpose)
            if key not in state["inputs"]: raise KeyError(key)
            payload_id = state["inputs"][key]
            request = next((rid for rid, row in state["requests"].items()
                            if row["payload_id"] == payload_id and row["state"] not in {"retired", "abandoned"}), None)
            if request and self._active(request): self._busy(request, self._active_reason(request))
            if request and state["requests"][request]["state"] in {"dispatching", "uncertain"}:
                self._uncertain(request, "uncertain-dispatch")
            record = state[payload_id]; state["inputs"].pop(key); record["owner"] = owner
            state["inputs"][self._key(subject, purpose, owner)] = payload_id
            self._save(state); return self._descriptor(record)

    def freeze(self, subject, purpose, request_id, action):
        self.fault("before_snapshot")
        descriptor = self.open(subject, purpose, create=False)
        exact = Path(descriptor["path"]).read_bytes(); digest = hashlib.sha256(exact).hexdigest()
        snapshot = self.root / "snapshots" / (request_id + ".json")
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        with snapshot.open("wb") as handle:
            handle.write(exact); handle.flush(); os.fsync(handle.fileno())
        with self._locked():
            state = self._load()
            if request_id in state["requests"]: raise ValueError("request_id already exists")
            state["requests"][request_id] = {"request_id": request_id, "payload_id": descriptor["payload_id"],
                "snapshot": str(snapshot), "digest": digest, "action": action, "state": "frozen"}
            self._save(state)
        self.fault("after_snapshot_fsync")
        return copy.deepcopy(state["requests"][request_id])

    def status(self, request_id):
        state = self._load()
        if request_id not in state["requests"]: raise KeyError(request_id)
        return copy.deepcopy(state["requests"][request_id])

    def recover(self, request_id):
        row = self.status(request_id); path = Path(row["snapshot"])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row["digest"]:
            raise ValueError("snapshot digest is corrupt")
        return row

    def _recovery(self, request_id, reason, action="reconcile"):
        return {"request_id": request_id, "reason": reason, "command": [
            sys.executable, str(Path(__file__).with_name("zzzops.py")), "working-input", action,
            "--repo", str(self.repo), "--request-id", request_id]}

    def _busy(self, request_id, reason):
        raise WorkingInputBusy(f"{reason}: {request_id}", self._recovery(request_id, reason, "status"))

    def _uncertain(self, request_id, reason):
        raise WorkingInputUncertain(f"{reason}: reconcile {request_id}", self._recovery(request_id, reason))

    def _active(self, request_id):
        with _ACTIVE_LOCK: return bool(_ACTIVE.get((str(self.repo), request_id)))

    def _active_reason(self, request_id):
        with _ACTIVE_LOCK:
            kinds = _ACTIVE.get((str(self.repo), request_id), {})
            return "active-lease" if kinds.get("lease") else "active-reference"

    @contextmanager
    def reference(self, request_id, kind="reader"):
        key = (str(self.repo), request_id)
        with _ACTIVE_LOCK:
            kinds = _ACTIVE.setdefault(key, {}); kinds[kind] = kinds.get(kind, 0) + 1
        try: yield
        finally:
            with _ACTIVE_LOCK:
                kinds = _ACTIVE[key]; kinds[kind] -= 1
                if not kinds[kind]: kinds.pop(kind)
                if not kinds: _ACTIVE.pop(key)

    @contextmanager
    def reader(self, request_id):
        row = self.recover(request_id)
        with self.reference(request_id, "reader"):
            yield Path(row["snapshot"]).read_bytes()

    def dispatch(self, request_id, sender):
        with self._locked():
            state = self._load(); row = state["requests"][request_id]
            if row["state"] == "confirmed": return copy.deepcopy(row["receipt"])
            if row["state"] in {"dispatching", "uncertain"}: self._uncertain(request_id, "uncertain-dispatch")
            if row["state"] not in {"frozen", "reconciled"}: raise ValueError("request is not dispatchable")
            exact = Path(row["snapshot"]).read_bytes()
            if hashlib.sha256(exact).hexdigest() != row["digest"]: raise ValueError("snapshot digest is corrupt")
            row["state"] = "dispatching"; self._save(state)
        self.fault("after_dispatching_fsync")
        try:
            with self.reference(request_id, "provider-dispatch"):
                result = sender(request_id, exact)
        except BaseException as exc:
            with self._locked():
                state = self._load(); state["requests"][request_id]["state"] = "uncertain"
                state["requests"][request_id]["uncertain_reason"] = "provider-exception"; self._save(state)
            if type(exc).__name__ == "AppliedThenLost": raise
            self._uncertain(request_id, "provider-exception")
        steps = result.get("next_steps") if isinstance(result, dict) else None
        if steps:
            reason = "repair-response" if any(step.get("kind") == "repair" for step in steps) else "missing-receipt"
            with self._locked():
                state = self._load(); state["requests"][request_id]["state"] = "uncertain"
                state["requests"][request_id]["uncertain_reason"] = reason; self._save(state)
            self._uncertain(request_id, reason)
        if not isinstance(result, dict) or "receipt" not in result:
            with self._locked():
                state = self._load(); state["requests"][request_id]["state"] = "uncertain"
                state["requests"][request_id]["uncertain_reason"] = "missing-receipt"; self._save(state)
            self._uncertain(request_id, "missing-receipt")
        with self._locked():
            state = self._load(); row = state["requests"][request_id]
            row["state"] = "confirmed"; row["receipt"] = copy.deepcopy(result); self._save(state)
        return result

    def reconcile(self, request_id):
        row = self.recover(request_id)
        if row["state"] not in {"uncertain", "dispatching"}: return row
        for _ in range(3):
            outcome = self.provider_check(request_id, row["digest"])
            if outcome is True:
                with self._locked():
                    state = self._load(); state["requests"][request_id]["state"] = "reconciled"; self._save(state)
                return self.status(request_id)
            if outcome is False:
                with self._locked():
                    state = self._load(); state["requests"][request_id]["state"] = "frozen"; self._save(state)
                return self.status(request_id)
        reason = ("unconfirmed-reconciliation" if row.get("uncertain_reason") == "missing-receipt"
                  else "three-check-limit")
        self._uncertain(request_id, reason)

    def _delete(self, request_id, terminal):
        self.fault("before_delete_lock")
        with self._locked():
            if self._active(request_id): self._busy(request_id, "active-reference")
            state = self._load(); row = state["requests"][request_id]
            path = Path(row["snapshot"])
            try: path.unlink()
            except FileNotFoundError: pass
            row["state"] = terminal; self._save(state)
            return copy.deepcopy(row)

    def retire(self, request_id, receipt):
        row = self.status(request_id)
        if self._active(request_id): self._busy(request_id, "active-reference")
        if row["state"] in {"dispatching", "uncertain"}: self._uncertain(request_id, "uncertain-dispatch")
        if row["state"] != "confirmed" or row.get("receipt") != receipt:
            raise PermissionError("exact confirmed receipt is required")
        return self._delete(request_id, "retired")

    def abandon(self, request_id, *, approved_by):
        if not approved_by: raise PermissionError("explicit abandonment approval is required")
        row = self.status(request_id)
        if self._active(request_id): self._busy(request_id, "active-reference")
        if row["state"] in {"dispatching", "uncertain"}: self._uncertain(request_id, "uncertain-dispatch")
        return self._delete(request_id, "abandoned")

    def guidance(self, subject, purpose, legacy_paths=()):
        descriptor = self.open(subject, purpose)
        path = descriptor["path"]
        command = [sys.executable, "-c", "import pathlib,sys;print(pathlib.Path(sys.argv[1]).read_text())", path]
        return {"path": path, "payload_id": descriptor["payload_id"], "commands": [command],
                "legacy": [{"path": str(Path(item).resolve()), "status": "untouched"} for item in legacy_paths]}


def execute_command(action: str, *, repo: Path, request_id: str):
    store = WorkingInputStore(repo, repository="local", owner="root")
    if action == "status": return store.status(request_id)
    if action == "reconcile": return store.reconcile(request_id)
    raise ValueError("unsupported working-input action")
