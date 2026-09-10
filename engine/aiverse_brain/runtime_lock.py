from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Iterator
from uuid import uuid4

from .errors import LockConflict
from .models import utc_now


class RuntimeKeyLock:
    """Short-lived, disposable cross-process lock for runtime coordination keys."""

    def __init__(self, runtime_dir: Path, *, namespace: str, ttl_seconds: int = 60):
        self.runtime_dir = Path(runtime_dir)
        self.root = self.runtime_dir.parent.parent
        self.directory = self.runtime_dir / "locks" / namespace
        self.ttl_seconds = ttl_seconds

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.lock"

    @contextmanager
    def acquire(self, key: str) -> Iterator[None]:
        if not key:
            raise ValueError("lock key is required")
        from .write_gate import require_write_ready
        require_write_ready(str(self.root))
        self.directory.mkdir(parents=True, exist_ok=True)
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
