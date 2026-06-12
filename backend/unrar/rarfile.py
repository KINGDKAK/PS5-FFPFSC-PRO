"""High-level Python API for UnRAR extraction.

Mirrors the subset of the `rarfile` library API used by ps5-ffpfs-cli.
"""

import os
from pathlib import Path

from unrar import _unrar


class BadRarFile(Exception):
    """Invalid or corrupted RAR archive."""


class RarWrongPassword(Exception):
    """Incorrect or missing password for encrypted archive."""


class NeedFirstVolume(Exception):
    """Multi-volume archive must start from the first volume."""


class RarInfo:
    """Metadata about a single member of a RAR archive."""

    __slots__ = ("filename", "file_size", "compress_size", "is_directory")

    def __init__(self, data: dict):
        self.filename = data["filename"]
        self.file_size = data["file_size"]
        self.compress_size = data["compress_size"]
        self.is_directory = data["is_directory"]

    def isdir(self) -> bool:
        return self.is_directory


class RarFile:
    """A RAR archive file."""

    def __init__(self, filename: str | Path, mode: str = "r", pwd: str | None = None):
        self.filename = str(filename)
        self.pwd = pwd
        self._filelist: list[RarInfo] | None = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def infolist(self) -> list[RarInfo]:
        """Return a list of RarInfo instances for all members."""
        if self._filelist is None:
            try:
                raw_list = _unrar.list_files(self.filename, self.pwd)
            except _unrar.UnrarError as exc:
                raise BadRarFile(str(exc)) from exc
            self._filelist = [RarInfo(item) for item in raw_list]
        return self._filelist

    def namelist(self) -> list[str]:
        """Return a list of member filenames."""
        return [info.filename for info in self.infolist()]

    def extractall(self, path: str | Path | None = None):
        """Extract all members to the given path (default: current directory)."""
        if path is None:
            path = "."
        dest = str(path)

        # Validate member paths before extraction (defense-in-depth)
        dest_resolved = Path(dest).resolve()
        for info in self.infolist():
            member_path = (dest_resolved / info.filename).resolve()
            try:
                member_path.relative_to(dest_resolved)
            except ValueError:
                raise BadRarFile(f"Unsafe path in archive: {info.filename}")

        try:
            _unrar.extract_all(self.filename, dest, self.pwd)
        except PermissionError as exc:
            raise RarWrongPassword(str(exc)) from exc
        except _unrar.UnrarError as exc:
            msg = str(exc).lower()
            if "password" in msg or "missing password" in msg:
                raise RarWrongPassword(str(exc)) from exc
            raise BadRarFile(str(exc)) from exc
