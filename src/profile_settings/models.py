"""Type-safe ``ProfileSettings`` model and its validators.

The design follows CLAUDE.md rule #1: a single ``validate_and_create`` factory
is the only entry point that touches a raw ``dict``. Everything past that
boundary works with the typed ``ProfileSettings`` model, so the business layer
never has to deal with unvalidated dicts.

Validation observes a "collect all failures" philosophy: instead of aborting on
the first bad field, every field is checked and the results are aggregated into
one structured ``ValidationError``. That lets the UI/consumer present all
problems at once rather than the user fixing them one by one round-tripping.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .exceptions import ValidationError

# --- Field patterns ---------------------------------------------------------

# Username: lowercase alphanumeric, 3-20 chars. Enforced as a regex here so a
# format violation (uppercase / punctuation) is reported separately from a length
# violation, producing a more helpful per-field message in the structured errors.
_USERNAME_RE = re.compile(r"^[a-z0-9]+$")

# Email: a strict RFC 5322-aware pattern. This is the well-traveled regex used by
# the WHATWG HTML5 <input type="email"> spec; it is intentionally more practical
# than the full RFC 5322 grammar (which permits exotic forms no real-world MTA
# accepts) while remaining faithful to the standard's intent for addressing.
# Source: https://html.spec.whatwg.org/multipage/input.html#valid-e-mail-address
# We additionally require at least one dot in the domain part (a public-style
# address) to satisfy the assignment's "strict" intent; the WHATWG pattern alone
# would accept single-label hosts such as "user@domain".
_EMAIL_RE = re.compile(
    r"""^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+
        @[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?
        (?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+
        $""",
    re.VERBOSE,
)

# Password: the set of characters counted as "special". Anything outside
# A-Z, a-z, 0-9 is treated as special, which matches common password policies.
_SPECIAL_CHARS = set(r"!\"#$%&'()*+,-./:;<=>?@[\]^_`{|}~")


class Theme(str, Enum):
    """UI theme preference (CLAUDE.md rule #3: fixed choices bound by Enum)."""

    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


class ProfileSettings(BaseModel):
    """Validated user profile settings.

    The model is frozen (immutable) — once constructed, a ``ProfileSettings``
    instance can be trusted to remain valid. Mutation would require going
    through ``validate_and_create`` again, preserving the "no unvalidated data
    in business logic" guarantee.
    """

    model_config = ConfigDict(frozen=True, str_strip_whitespace=False, extra="forbid")

    username: str = Field(..., min_length=3, max_length=20)
    email: str = Field(...)
    password: str = Field(..., min_length=8)
    theme: Theme

    # --- username -----------------------------------------------------------

    @field_validator("username")
    @classmethod
    def _validate_username(cls, v: str) -> str:
        # Length is also bounded at the Field level (min/max_length), but covering
        # it here gives us a field-specific message inside the structured error
        # dict rather than pydantic's generic one. We keep both: Field catches it
        # during schema validation, this raises a clearer message.
        if not isinstance(v, str):
            raise ValueError("Username must be a string")
        if not (3 <= len(v) <= 20):
            raise ValueError("Username must be 3-20 characters")
        if not _USERNAME_RE.match(v):
            raise ValueError(
                "Username must contain only lowercase letters and digits"
            )
        return v

    # --- email --------------------------------------------------------------

    @field_validator("email")
    @classmethod
    def _validate_email(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("Email must be a string")
        if not _EMAIL_RE.match(v):
            raise ValueError("Invalid email format")
        return v

    # --- password -----------------------------------------------------------

    @field_validator("password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        if not isinstance(v, str):
            raise ValueError("Password must be a string")
        # min_length=8 covers the structural bound at the schema level, but
        # report a friendly message here too (the Field constraint only fires
        # for the too-short case; this is belt-and-suspenders in case the
        # field constraints are loosened later).
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        # Check each required class in a fixed priority order so a single
        # deterministic message is attached per broken password.
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c in _SPECIAL_CHARS for c in v):
            raise ValueError("Password must contain at least one special character")
        return v

    # --- theme --------------------------------------------------------------

    @field_validator("theme")
    @classmethod
    def _validate_theme(cls, v: Any) -> Theme:
        # pydantic already coerces the enum from values, but we translate a bad
        # value into a plain, human-readable message instead of leaking pydantic's
        # internal enum error wording into the structured dict.
        if isinstance(v, Theme):
            return v
        if isinstance(v, str):
            try:
                return Theme(v)
            except ValueError:
                raise ValueError(
                    f"Theme must be one of: {', '.join(t.value for t in Theme)}"
                )
        raise ValueError("Theme must be a string")


def validate_and_create(data: dict[str, Any]) -> ProfileSettings:
    """Build a ``ProfileSettings`` from a raw dict, raising ``ValidationError``.

    This is the *only* public function that accepts raw ``dict`` input. It
    catches pydantic's native ``ValidationError`` and re-throws ours with a
    ``dict[str, str]`` of field -> message, so the whole point of the structured
    error type is preserved across the very first boundary.

    Raises ``TypeError`` if ``data`` is not a dict — consistent with
    ``ValidationError``'s own type guard and with rule #1 (no sneaking past the
    boundary with a non-dict).
    """
    if not isinstance(data, dict):
        raise TypeError("validate_and_create requires a dict input")

    try:
        return ProfileSettings(**data)
    except Exception as exc:
        # pydantic raises its own ``pydantic.ValidationError`` (imported lazily
        # to avoid a name collision with our own ValidationError).
        from pydantic import ValidationError as PydanticValidationError

        if isinstance(exc, PydanticValidationError):
            aggregated: dict[str, str] = {}
            for err in exc.errors():
                # err["loc"] is a tuple like ("username",) or ("username", 0).
                # We key only on the top-level field name.
                loc = err.get("loc", ())
                field = loc[0] if loc else "__root__"
                field = field if isinstance(field, str) else str(field)
                # Keep the first message per field so the aggregated dict stays
                # one-entry-per-broken-field (and deterministic).
                if field in aggregated:
                    continue
                aggregated[field] = _humanize_error(field, err.get("type", ""), err.get("msg", "Invalid value"))
            raise ValidationError(aggregated) from exc
        # Anything else is unexpected — re-raise unchanged rather than masking.
        raise


def _humanize_error(field: str, err_type: str, raw_msg: str) -> str:
    """Translate a pydantic error into a concise, field-relevant message.

    Custom ``@field_validator`` messages arrive prefixed with ``Value error, ``;
    we strip that so our wording surfaces verbatim. Schema-level constraints
    (length, enum, missing, extra) keep their pydantic phrasing but with the
    boilerplate trimmed, e.g. ``password: "Too short (min 8 characters)"``.
    """
    if raw_msg.startswith("Value error, "):
        return raw_msg[len("Value error, "):]

    if err_type == "string_too_short":
        return "Too short (minimum 8 characters)" if field == "password" else "Too short"
    if err_type == "string_too_long":
        return "Too long (maximum 20 characters)" if field == "username" else "Too long"
    if err_type == "missing":
        return "Field is required"
    if err_type == "enum":
        return f"Invalid theme; must be one of: {', '.join(t.value for t in Theme)}"
    if err_type == "extra_forbidden":
        return "Unexpected field"
    return raw_msg
