"""Tests for ``ProfileStore``: persistence correctness, atomicity, and
thread-safety (CLAUDE.md rule #2 — happy, boundary, failure states).
"""

from __future__ import annotations

import json
import os
import stat
import threading
from pathlib import Path

import pytest

from profile_settings import (
    ProfileSettings,
    ProfileStore,
    Theme,
    ValidationError,
    validate_and_create,
)


# --- Happy path round-trip --------------------------------------------------


def test_save_then_load_round_trips(valid_settings_dict, temp_store):
    """A saved profile loads back with equal field values."""
    settings = validate_and_create(valid_settings_dict)
    temp_store.save(settings)

    loaded = temp_store.load()
    assert loaded is not None
    assert loaded.username == settings.username
    assert loaded.email == settings.email
    assert loaded.theme == settings.theme


def test_save_creates_expected_file(valid_settings_dict, temp_store):
    """The save actually materializes a JSON file at the store path."""
    settings = validate_and_create(valid_settings_dict)
    temp_store.save(settings)

    assert temp_store.path.exists()
    on_disk = json.loads(temp_store.path.read_text(encoding="utf-8"))
    assert on_disk["username"] == settings.username
    # theme is serialized as its enum value, not a repr.
    assert on_disk["theme"] == settings.theme.value


# --- Boundary: missing / corrupt file ---------------------------------------


def test_load_missing_file_returns_none(temp_store):
    """First-run condition: no file → None rather than an error."""
    assert temp_store.load() is None


def test_clear_is_idempotent(temp_store, valid_settings_dict):
    """clear() must not raise whether or not the file exists."""
    temp_store.save(validate_and_create(valid_settings_dict))
    temp_store.clear()
    temp_store.clear()  # second clear is a no-op


def test_load_corrupt_json_raises_structured_validation_error(temp_store):
    """Garbage JSON surfaces as a structured ``ValidationError`` keyed on 'config'."""
    temp_store.path.parent.mkdir(parents=True, exist_ok=True)
    temp_store.path.write_text("{ not: valid json ", encoding="utf-8")

    with pytest.raises(ValidationError) as ei:
        temp_store.load()
    assert "config" in ei.value.errors


def test_load_non_object_root_raises(tmp_path):
    """A JSON array at the root fails as a config-level error, not a field error."""
    store = ProfileStore(tmp_path / "config.json")
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text("[1, 2, 3]", encoding="utf-8")

    with pytest.raises(ValidationError) as ei:
        store.load()
    assert "config" in ei.value.errors


def test_load_invalid_values_re_validated(temp_store):
    """Reading does NOT trust the file — a stale invalid value is re-rejected."""
    temp_store.path.parent.mkdir(parents=True, exist_ok=True)
    bad = {
        "username": "AB",           # invalid
        "email": "not-an-email",
        "password": "weak",
        "theme": "chartreuse",
    }
    temp_store.path.write_text(json.dumps(bad), encoding="utf-8")

    with pytest.raises(ValidationError):
        temp_store.load()


# --- Atomicity: partial writes never leave a truncated file -----------------


def test_save_replaces_file_atomically(valid_settings_dict, temp_store):
    """Saving twice leaves exactly one file, with the latest content, and no temp leftovers."""
    first = validate_and_create({**valid_settings_dict, "username": "firstuser"})
    second = validate_and_create({**valid_settings_dict, "username": "seconduser"})

    temp_store.save(first)
    temp_store.save(second)

    # Only the canonical config file should exist — no stray .tmp siblings.
    siblings = list(temp_store.path.parent.glob("config*.tmp"))
    assert siblings == []

    loaded = temp_store.load()
    assert loaded is not None
    assert loaded.username == "seconduser"


def test_save_rejects_untyped_input(temp_store):
    """save() only accepts a ProfileSettings — a plain dict is refused."""
    with pytest.raises(TypeError):
        temp_store.save({"username": "x"})  # type: ignore[arg-type]


@pytest.mark.skipif(
    os.name == "nt",
    reason="POSIX fs permissions don't translate cleanly to Windows ACLs",
)
def test_save_failure_does_not_leave_partial_file(valid_settings_dict, tmp_path):
    """When writing is impossible (read-only dir), save raises and no file appears."""
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    # Make the directory unwritable so the temp file can't be created.
    os.chmod(readonly_dir, stat.S_IRUSR | stat.S_IXUSR)

    store = ProfileStore(readonly_dir / "config.json")
    settings = validate_and_create(valid_settings_dict)

    with pytest.raises(OSError):
        store.save(settings)

    # Restore so the tmp_path cleanup can remove it on Pytest exit.
    os.chmod(readonly_dir, stat.S_IRWXU)
    assert not (readonly_dir / "config.json").exists()
    assert not (readonly_dir / "config.json.tmp").exists()


# --- Thread-safety: concurrent writers don't corrupt the file ----------------


def test_concurrent_writers_no_corruption(valid_settings_dict, tmp_path):
    """Many threads each build distinct valid settings and save to one store.

    After all threads finish, the file must be valid JSON, parse into a
    ProfileSettings, and contain exactly one of the writers' usernames.
    A non-thread-safe store would produce a truncated/interleaved file that
    fails to parse.
    """
    store = ProfileStore(tmp_path / "config.json")
    usernames = [f"user{i:02d}" for i in range(15)]
    errors: list[BaseException] = []

    def writer(name: str) -> None:
        try:
            settings = validate_and_create(
                {**valid_settings_dict, "username": name, "theme": "system"}
            )
            store.save(settings)
        except BaseException as exc:  # noqa: BLE001 — collect, then assert outside
            errors.append(exc)

    threads = [threading.Thread(target=writer, args=(name,)) for name in usernames]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
        assert not t.is_alive(), "writer thread deadlocked"

    assert errors == [], f"writers raised: {errors}"

    # A thread-safe store may let the last writer win — that's fine — but the
    # file must always be a single valid, parseable record belonging to one of
    # the writers, never a torn/jumbled document.
    loaded = store.load()
    assert loaded is not None
    assert loaded.username in set(usernames)
    assert loaded.theme == Theme.SYSTEM


def test_concurrent_readers_and_writers_stable(valid_settings_dict, tmp_path):
    """Readers interleaved with a writer never observe invalid/partial JSON."""
    store = ProfileStore(tmp_path / "config.json")
    store.save(validate_and_create(valid_settings_dict))

    load_errors: list[BaseException] = []

    def reader() -> None:
        for _ in range(50):
            try:
                res = store.load()
                # During concurrency the file may briefly be between swaps,
                # but the lock guarantees we never get a half-written document:
                # either the previous or the new complete record.
                if res is not None:
                    assert res.username  # any saved user is well-formed
            except BaseException as exc:  # noqa: BLE001
                load_errors.append(exc)

    def writer() -> None:
        for i in range(20):
            s = validate_and_create(
                {**valid_settings_dict, "username": f"writer{i:02d}", "theme": "dark"}
            )
            store.save(s)

    writer_t = threading.Thread(target=writer)
    reader_ts = [threading.Thread(target=reader) for _ in range(4)]

    writer_t.start()
    for t in reader_ts:
        t.start()
    writer_t.join(timeout=30)
    for t in reader_ts:
        t.join(timeout=30)

    assert not writer_t.is_alive()
    assert all(not t.is_alive() for t in reader_ts)
    assert load_errors == [], f"readers saw errors: {load_errors}"
