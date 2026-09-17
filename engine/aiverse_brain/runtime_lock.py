from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Iterator
from uuid import uuid4

from .errors import LockConflict, ValidationError
from .models import utc_now


class RuntimeKeyLock:
    """Short-lived, disposable cross-process lock for runtime coordination keys."""

    def __init__(self, runtime_dir: Path, *, namespace: str, ttl_seconds: int = 60):
        if not namespace or namespace in {".", ".."} or "/" in namespace or "\\" in namespace:
            raise ValidationError("runtime lock namespace must be a path-safe segment")
        self.runtime_dir = Path(runtime_dir)
        self.root = self.runtime_dir.parent.parent
        self.namespace = namespace
        self.directory = self.runtime_dir / "locks" / namespace
        self.ttl_seconds = ttl_seconds

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.lock"

    def _revalidate_directory(self) -> None:
        # A runtime path can be replaced after controller construction. Recheck
        # the physical native path immediately before every lock mutation.
        from .integration import HostMode, inspect_host
        from .path_safety import safe_host_path

        report = inspect_host(str(self.root))
        if report.mode == HostMode.AI_VERSE_OS_V2:
            expected_runtime = safe_host_path(self.root, "runtime", "ai-verse-brain")
            if os.path.abspath(os.fspath(self.runtime_dir)) != os.path.abspath(os.fspath(expected_runtime)):
                raise ValidationError("runtime lock directory is not the canonical native Brain runtime root")
            self.directory = safe_host_path(
                self.root, "runtime", "ai-verse-brain", "locks", self.namespace
            )

    @contextmanager
    def acquire(self, key: str) -> Iterator[None]:
        if not key:
            raise ValueError("lock key is required")
        from .write_gate import require_write_ready
        require_write_ready(str(self.root))
        self._revalidate_directory()
        self.directory.mkdir(parents=True, exist_ok=True)
        self._revalidate_directory()
        path = self._path(key)
        token = str(uuid4())
        payload = json.dumps({"token": token, "acquired_at": utc_now(), "pid": os.getpid()}) + "\n"
        acquired = False
        for attempt in range(2):
            try:
                fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                try:
                    age = time.time() - path.stat().st_mtime
                except FileNotFoundError:
                    continue
                if age > self.ttl_seconds and attempt == 0:
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
                    continue
                raise LockConflict(f"runtime key is currently locked: {key}")
            else:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                acquired = True
                break
        if not acquired:
            raise LockConflict(f"unable to acquire runtime key lock: {key}")
        try:
            yield
        finally:
            try:
                current = json.loads(path.read_text(encoding="utf-8"))
                if current.get("token") == token:
                    path.unlink(missing_ok=True)
            except FileNotFoundError:
                pass
