"""Thread-safe JSON persistence for ``ProfileSettings``.

``ProfileStore`` reads and writes the validated settings to a local
``config.json``. Writes are atomic (temp file + ``os.replace``) and serialized
via a re-entrant process-local lock, so concurrent writers/threads inside one
process can't corrupt the file. Reads re-validate through ``validate_and_create``
— the file is never trusted as already-valid input (rule #1).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Optional

from .exceptions import ValidationError
from .models import ProfileSettings, validate_and_create


class ProfileStore:
    """File-backed, thread-safe store for a single ``ProfileSettings`` record.

    The store guards access with a single ``threading.RLock``. This makes the
    store safe for use across threads *within one process* (the common case for
    a Python config manager); inter-process safety is out of scope here and would
    require OS-level file locking.
    """

    def __init__(self, config_path: str | os.PathLike[str] = "config.json") -> None:
        self._path = Path(config_path)
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        """Absolute path to the backing ``config.json`` (for inspection/tests)."""
        return self._path

    # --- writing ------------------------------------------------------------

    def save(self, settings: ProfileSettings) -> None:
        """Persist ``settings`` atomically.

        Writes to a sibling temp file first, then ``os.replace`` swaps it into
        place. ``os.replace`` is atomic on the same filesystem (POSIX rename and
        Windows MoveFileEx), so a crash mid-write leaves the previous good config
        intact rather than a truncated file. Raises ``TypeError`` if given
        something other than a ``ProfileSettings`` (no slipping untyped data in).
        """
        if not isinstance(settings, ProfileSettings):
            raise TypeError("save() requires a ProfileSettings instance")

        payload = settings.model_dump(mode="json")

        # Hold the lock across the whole write so a concurrent writer can't
        # interleave temp-file creation / replacement steps. RLock allows the
        # same thread to re-save without deadlocking.
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
            try:
                # newline="" so json writes portable \n on every platform.
                with tmp_path.open("w", encoding="utf-8", newline="") as fh:
                    json.dump(payload, fh, indent=2, sort_keys=True)
                    fh.write("\n")
                    fh.flush()
                    os.fsync(fh.fileno())
                os.replace(tmp_path, self._path)
            except OSError:
                # Clean up the temp file if anything went wrong before the swap,
                # then propagate — never leave stray temp files behind.
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass
                raise

    # --- reading ------------------------------------------------------------

    def load(self) -> Optional[ProfileSettings]:
        """Load and re-validate settings; return ``None`` if no config exists.

        A missing file is a normal condition (first run) → ``None``. A *bad*
        file (corrupt JSON, or content that no longer validates) raises our
        structured ``ValidationError`` with a ``config`` field entry, rather
        than leaking ``json.JSONDecodeError`` upstream.
        """
        with self._lock:
            if not self._path.exists():
                return None
            try:
                raw_text = self._path.read_text(encoding="utf-8")
            except OSError as exc:
                raise ValidationError({"config": f"Unable to read config file: {exc}"})

            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError as exc:
                raise ValidationError({"config": f"Config file is not valid JSON: {exc}"})

            if not isinstance(data, dict):
                # Treat a non-object root as a config-level failure instead of
                # letting it through to the field validators.
                raise ValidationError({"config": "Config file root must be a JSON object"})

            return validate_and_create(data)

    # --- convenience ---------------------------------------------------------

    def clear(self) -> None:
        """Remove the config file if it exists (idempotent)."""
        with self._lock:
            if self._path.exists():
                self._path.unlink()
