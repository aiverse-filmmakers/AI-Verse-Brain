from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Union

from .errors import ValidationError

WINDOWS_REPARSE_POINT = 0x0400
PathPart = Union[str, os.PathLike[str]]


def _lexists(path: Path) -> bool:
    return os.path.lexists(os.fspath(path))


def is_symlink_or_reparse(path: Path) -> bool:
    """Return True for POSIX symlinks and Windows junction/reparse points."""
    try:
        info = os.lstat(os.fspath(path))
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    return bool(getattr(info, "st_file_attributes", 0) & WINDOWS_REPARSE_POINT)


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _path_part(value: PathPart) -> str:
    part = os.fspath(value)
    if not isinstance(part, str) or not part or part in {".", ".."}:
        raise ValidationError("native path component must be a non-empty single path segment")
    if "/" in part or "\\" in part:
        raise ValidationError(f"native path component contains a path separator: {part!r}")
    return part


def safe_host_path(
    root: PathPart,
    *parts: PathPart,
    require_directory: bool = False,
    require_regular_file: bool = False,
) -> Path:
    """Build a path physically confined to one selected host root.

    Existing path components must be ordinary filesystem entries. POSIX symlinks,
    Windows junctions/reparse points, and components that resolve outside the
    selected canonical host root fail closed. Missing descendants are allowed so
    callers can safely plan first-time creation after the nearest existing parent
    has been validated.
    """
    base = Path(root).expanduser().resolve()
    if not base.exists() or not base.is_dir():
        raise ValidationError(f"selected host root is not an existing directory: {base}")

    current = base
    for index, raw_part in enumerate(parts):
        current = current / _path_part(raw_part)
        if not _lexists(current):
            continue
        if is_symlink_or_reparse(current):
            raise ValidationError(f"unsafe symlink/junction/reparse point in native Brain path: {current}")
        try:
            resolved = current.resolve(strict=True)
        except OSError as exc:
            raise ValidationError(f"cannot resolve native Brain path component {current}: {exc}") from exc
        if not _inside(resolved, base):
            raise ValidationError(f"native Brain path escapes selected host root: {current}")
        if index < len(parts) - 1 and not resolved.is_dir():
            raise ValidationError(f"native Brain path parent is not a directory: {current}")

    if require_directory:
        if not _lexists(current):
            raise ValidationError(f"required native Brain directory does not exist: {current}")
        if is_symlink_or_reparse(current) or not current.is_dir():
            raise ValidationError(f"required native Brain directory is unsafe: {current}")
    if require_regular_file:
        if not _lexists(current):
            raise ValidationError(f"required native Brain file does not exist: {current}")
        if is_symlink_or_reparse(current) or not current.is_file():
            raise ValidationError(f"required native Brain file is unsafe: {current}")

    return current


def validate_native_host_parents(root: PathPart) -> tuple[Path, Path]:
    """Validate the two native OS parents Brain relies on before any native write."""
    operator = safe_host_path(root, "operator", require_directory=True)
    workspaces = safe_host_path(root, "workspaces", require_directory=True)
    return operator, workspaces
