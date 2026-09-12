from __future__ import annotations

"""AI-Verse OS local attachment registry support for Brain.

The OS owns the registry contract. Brain mutates only its own entry and never
edits tracked OS files.
"""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, Iterator, Optional

from ._version import __version__
from .errors import ValidationError

REGISTRY_RELATIVE = Path(".aiverse/extensions/registry.json")
LOCK_RELATIVE = Path(".aiverse/extensions/registry.json.lock")
REGISTRY_SCHEMA = "1.0"
BRAIN_EXTENSION_ID = "ai-verse-brain"
MAX_REGISTRY_BYTES = 1024 * 1024


def _safe_extensions_dir(root: Path) -> Path:
    root = Path(root).resolve()
    meta = root / ".aiverse"
    extensions = meta / "extensions"
    for path in (meta, extensions):
        if path.exists() and path.is_symlink():
            raise ValidationError(f"unsafe symlink in extension registry path: {path}")
        if path.exists() and not path.is_dir():
            raise ValidationError(f"extension registry path is not a directory: {path}")
        if not path.exists():
            path.mkdir(mode=0o700)
    return extensions


def _registry_path(root: Path) -> Path:
    return Path(root).resolve() / REGISTRY_RELATIVE


def _read_registry(root: Path) -> tuple[Dict[str, Any], Optional[str]]:
    path = _registry_path(root)
    if not path.exists():
        return {"schema_version": REGISTRY_SCHEMA, "extensions": {}}, None
    if path.is_symlink() or not path.is_file():
        raise ValidationError("AI-Verse extension registry must be a regular non-symlink file")
    if path.stat().st_size > MAX_REGISTRY_BYTES:
        raise ValidationError("AI-Verse extension registry is too large")
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except Exception as exc:
        raise ValidationError(f"AI-Verse extension registry is invalid: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema_version") != REGISTRY_SCHEMA:
        raise ValidationError("unsupported AI-Verse extension registry schema")
    if not isinstance(data.get("extensions"), dict):
        raise ValidationError("AI-Verse extension registry extensions must be an object")
    return data, raw


@contextmanager
def _registry_lock(root: Path) -> Iterator[None]:
    extensions = _safe_extensions_dir(root)
    lock = extensions / "registry.json.lock"
    try:
        fd = os.open(str(lock), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ValidationError(f"AI-Verse extension registry is busy: {lock}") from exc
    except OSError as exc:
        raise ValidationError(f"cannot acquire AI-Verse extension registry lock: {exc}") from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump({"extension_id": BRAIN_EXTENSION_ID}, handle)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        yield
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass


def _atomic_registry_write(root: Path, data: Dict[str, Any], expected_raw: Optional[str]) -> None:
    extensions = _safe_extensions_dir(root)
    path = extensions / "registry.json"
    current_raw = path.read_text(encoding="utf-8") if path.exists() else None
    if current_raw != expected_raw:
        raise ValidationError("AI-Verse extension registry changed during Brain attachment")
    fd, temp_name = tempfile.mkstemp(prefix=".registry.", suffix=".tmp", dir=str(extensions))
    try:
        try:
            os.chmod(temp_name, 0o600)
        except OSError:
            pass
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists() and (path.is_symlink() or not path.is_file()):
            raise ValidationError("AI-Verse extension registry became unsafe before replacement")
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def brain_attachment(root: str) -> Optional[Dict[str, Any]]:
    base = Path(root).resolve()
    data, _ = _read_registry(base)
    raw = data["extensions"].get(BRAIN_EXTENSION_ID)
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValidationError("ai-verse-brain extension entry must be an object")
    if raw.get("id") not in {None, BRAIN_EXTENSION_ID}:
        raise ValidationError("ai-verse-brain extension entry id mismatch")
    if "enabled" in raw and not isinstance(raw["enabled"], bool):
        raise ValidationError("ai-verse-brain extension enabled must be boolean")
    return dict(raw)


def brain_attachment_valid(root: str) -> bool:
    entry = brain_attachment(root)
    return bool(
        entry
        and entry.get("supported") is True
        and entry.get("installed") is True
        and entry.get("enabled") is True
    )


def attach_brain(root: str) -> Dict[str, Any]:
    base = Path(root).resolve()
    with _registry_lock(base):
        data, raw = _read_registry(base)
        extensions = data["extensions"]
        existing = extensions.get(BRAIN_EXTENSION_ID, {})
        if existing is None:
            existing = {}
        if not isinstance(existing, dict):
            raise ValidationError("existing ai-verse-brain extension entry must be an object")
        enabled = existing.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValidationError("existing ai-verse-brain enabled field must be boolean")
        entry = {
            **existing,
            "id": BRAIN_EXTENSION_ID,
            "supported": True,
            "installed": True,
            "enabled": enabled,
            "version": __version__,
            "source": "AI-Verse-Brain",
            "adapters": existing.get("adapters", []),
        }
        if not isinstance(entry["adapters"], list):
            raise ValidationError("existing ai-verse-brain adapters field must be an array")
        extensions[BRAIN_EXTENSION_ID] = entry
        data["schema_version"] = REGISTRY_SCHEMA
        _atomic_registry_write(base, data, raw)
        return dict(entry)


def set_brain_enabled(root: str, enabled: bool) -> Dict[str, Any]:
    if not isinstance(enabled, bool):
        raise ValidationError("enabled must be boolean")
    base = Path(root).resolve()
    with _registry_lock(base):
        data, raw = _read_registry(base)
        extensions = data["extensions"]
        existing = extensions.get(BRAIN_EXTENSION_ID)
        if not isinstance(existing, dict):
            raise ValidationError("Brain is not attached to this AI-Verse OS")
        entry = dict(existing)
        entry["enabled"] = enabled
        extensions[BRAIN_EXTENSION_ID] = entry
        _atomic_registry_write(base, data, raw)
        return dict(entry)


def detach_brain_registration(root: str) -> bool:
    base = Path(root).resolve()
    with _registry_lock(base):
        data, raw = _read_registry(base)
        extensions = data["extensions"]
        if BRAIN_EXTENSION_ID not in extensions:
            return False
        del extensions[BRAIN_EXTENSION_ID]
        _atomic_registry_write(base, data, raw)
        return True
