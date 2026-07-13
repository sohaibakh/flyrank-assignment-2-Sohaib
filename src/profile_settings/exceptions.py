"""Custom exception types for profile-settings validation.

Per CLAUDE.md rule #1 the business layer must not receive raw, unvalidated
``dict`` objects — and that includes error payloads. ``ValidationError`` is the
single, structured way failures are surfaced: it carries a ``dict[str, str]``
mapping a field name to a human-readable message, so callers learn about every
problem (not just the first) in one shot.
"""

from __future__ import annotations

from typing import Any


class ValidationError(ValueError):
    """Raised when one or more profile fields fail validation.

    The structured, field-specific errors live on ``self.errors`` as a
    ``dict[str, str]`` (e.g. ``{"password": "Too short", "email": "Invalid
    format"}``). The first error is also mirrored into the standard ``args`` /
    ``str()`` so the exception behaves reasonably when logged or printed on its
    own.
    """

    __slots__ = ("errors",)

    def __init__(self, errors: dict[str, str]):
        # Reject anything that isn't a real mapping of str -> str. This is the
        # guard that keeps undiciplined callers (or a pydantic leak) from
        # smuggling raw, unvalidated dicts through the error channel.
        if not isinstance(errors, dict) or not all(
            isinstance(k, str) and isinstance(v, str) for k, v in errors.items()
        ):
            raise TypeError(
                "ValidationError requires a dict[str, str] of field -> message"
            )
        if not errors:
            raise ValueError("ValidationError requires at least one error entry")

        # Copy defensively so the caller can't mutate our state after the fact.
        self.errors: dict[str, str] = dict(errors)
        # Mirror the message into ValueError's args for sensible repr/log output.
        super().__init__(str(self.errors))

    def __str__(self) -> str:
        return "; ".join(f"{field}: {msg}" for field, msg in self.errors.items())

    def __repr__(self) -> str:  # pragma: no cover - debugging convenience
        return f"ValidationError({self.errors!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ValidationError):
            return NotImplemented
        return self.errors == other.errors

    def __hash__(self) -> int:  # pragma: no cover - makes the type hashable for sets/dicts
        return hash(tuple(sorted(self.errors.items())))

    # Allow dict-style ``err["field"]`` / ``'field' in err`` access — ergonomic
    # for tests without exposing the underlying dict for mutation.
    def __getitem__(self, field: str) -> str:
        return self.errors[field]

    def __contains__(self, field: object) -> bool:
        return field in self.errors

    def keys(self) -> Any:
        """Return the offending field names (dict-like convenience)."""
        return self.errors.keys()
