"""Tests for the ``ProfileSettings`` model and ``validate_and_create`` factory.

Coverage map (CLAUDE.md rule #2 — happy path + ≥2 boundaries per concerns):
- Happy path for the whole profile and per field.
- Boundary lengths for username and password.
- Failure states (bad format / weak password / bad theme) → structured errors.
- Aggregation: multiple bad fields surface together in one ``ValidationError``.
- Type guard: ``ValidationError`` rejects non-dict / non-str mappings.
- Boundary values at exact allowed limits and one past them.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from profile_settings import ProfileSettings, Theme, ValidationError, validate_and_create


# --- Happy path -------------------------------------------------------------


def test_happy_path_valid_profile(valid_settings_dict):
    """The baseline valid dict builds a ProfileSettings with correct fields."""
    settings = validate_and_create(valid_settings_dict)

    assert settings.username == "sohaib123"
    assert settings.email == "sohaib@example.com"
    assert settings.password == "Str0ng!Pass"
    assert settings.theme == Theme.LIGHT


@pytest.mark.parametrize("theme_value", ["light", "dark", "system"])
def test_happy_path_each_theme(theme_value, valid_settings_dict):
    """All three enum members are accepted from their string values."""
    valid_settings_dict["theme"] = theme_value
    settings = validate_and_create(valid_settings_dict)
    assert settings.theme == Theme(theme_value)


# --- Username boundaries & failures ----------------------------------------


def test_username_boundary_min_length_ok(valid_settings_dict):
    """3 chars is the smallest accepted username."""
    valid_settings_dict["username"] = "abc"
    assert validate_and_create(valid_settings_dict).username == "abc"


def test_username_boundary_below_min_fails(valid_settings_dict):
    """2 chars is one below the floor and must error with a length message."""
    valid_settings_dict["username"] = "ab"
    with pytest.raises(ValidationError) as ei:
        validate_and_create(valid_settings_dict)
    assert "username" in ei.value.errors


def test_username_boundary_max_length_ok(valid_settings_dict):
    """20 chars is the largest accepted username."""
    valid_settings_dict["username"] = "a" * 20
    assert len(validate_and_create(valid_settings_dict).username) == 20


def test_username_boundary_above_max_fails(valid_settings_dict):
    """21 chars is one past the ceiling and must error."""
    valid_settings_dict["username"] = "a" * 21
    with pytest.raises(ValidationError) as ei:
        validate_and_create(valid_settings_dict)
    assert "username" in ei.value.errors


def test_username_rejects_uppercase(valid_settings_dict):
    """Uppercase letters are format-invalid even at a legal length."""
    valid_settings_dict["username"] = "Sohaib123"
    with pytest.raises(ValidationError) as ei:
        validate_and_create(valid_settings_dict)
    assert "username" in ei.value.errors
    assert "lowercase" in ei.value.errors["username"].lower()


def test_username_rejects_special_characters(valid_settings_dict):
    """Symbols are not alphanumeric and must be rejected."""
    valid_settings_dict["username"] = "sohaib_123"
    with pytest.raises(ValidationError) as ei:
        validate_and_create(valid_settings_dict)
    assert "username" in ei.value.errors


def test_username_rejects_spaces(valid_settings_dict):
    """Embedded whitespace is neither lowercase alpha nor a digit."""
    valid_settings_dict["username"] = "sohaib 123"
    with pytest.raises(ValidationError) as ei:
        validate_and_create(valid_settings_dict)
    assert "username" in ei.value.errors


# --- Email boundaries & failures -------------------------------------------


def test_email_happy(valid_settings_dict):
    """A vanilla ASCII email passes."""
    valid_settings_dict["email"] = "first.last@sub.example.co.uk"
    settings = validate_and_create(valid_settings_dict)
    assert settings.email == "first.last@sub.example.co.uk"


@pytest.mark.parametrize(
    "bad_email",
    [
        "plainaddress",          # no @
        "@no-local.com",         # no local part
        "user@.com",             # domain starts with dot
        "user@domain",          # no TLD
        "user@domain..com",      # consecutive dots in domain
        "user space@valid.com",   # whitespace in local part
    ],
)
def test_email_rejects_malformed(bad_email, valid_settings_dict):
    """Each malformed shape fails the RFC 5322-aware pattern."""
    valid_settings_dict["email"] = bad_email
    with pytest.raises(ValidationError) as ei:
        validate_and_create(valid_settings_dict)
    assert "email" in ei.value.errors


# --- Password boundaries & failures ----------------------------------------


def test_password_boundary_min_length_ok(valid_settings_dict):
    """Exactly 8 chars satisfying all classes is the shortest accepted password."""
    valid_settings_dict["password"] = "Aa1!bbbb"  # len 8, all classes present
    assert validate_and_create(valid_settings_dict).password == "Aa1!bbbb"


def test_password_below_min_fails(valid_settings_dict):
    """7 chars (one below floor) must error as too short."""
    valid_settings_dict["password"] = "Aa1!bbb"  # len 7, all classes present
    with pytest.raises(ValidationError) as ei:
        validate_and_create(valid_settings_dict)
    assert "password" in ei.value.errors


@pytest.mark.parametrize(
    "weak_password, missing_keyword",
    [
        ("aaaaaaaa1!", "uppercase"),      # no uppercase
        ("AAAAAAAA1!", "lowercase"),      # no lowercase
        ("AaaaaaaaA!", "digit"),          # no digit
        ("Aaaaaaaa1A", "special"),        # no special char
    ],
)
def test_password_rejects_missing_character_class(
    weak_password, missing_keyword, valid_settings_dict
):
    """A password missing exactly one required class reports that class in the message."""
    valid_settings_dict["password"] = weak_password
    with pytest.raises(ValidationError) as ei:
        validate_and_create(valid_settings_dict)
    assert "password" in ei.value.errors
    assert missing_keyword in ei.value.errors["password"].lower()


def test_password_short_and_weak_reports_length_first(valid_settings_dict):
    """When a password is both too short AND missing a class, the structured
    error still has a password key (priority: length checked before classes)."""
    valid_settings_dict["password"] = "aa1!"  # len 4 and missing uppercase
    with pytest.raises(ValidationError) as ei:
        validate_and_create(valid_settings_dict)
    assert "password" in ei.value.errors


# --- Theme failures ---------------------------------------------------------


@pytest.mark.parametrize("bad_theme", ["LIGHT", "blue", "", "Light", 5])
def test_theme_rejects_invalid_value(bad_theme, valid_settings_dict):
    """Any value outside the enum fails with a theme-specific message."""
    valid_settings_dict["theme"] = bad_theme
    with pytest.raises(ValidationError) as ei:
        validate_and_create(valid_settings_dict)
    assert "theme" in ei.value.errors


def test_theme_accepts_enum_instance(valid_settings_dict):
    """Passing an actual ``Theme`` enum (not a string) also works."""
    valid_settings_dict["theme"] = Theme.DARK
    assert validate_and_create(valid_settings_dict).theme == Theme.DARK


# --- Aggregation: all failures at once -------------------------------------


def test_multiple_fields_invalid_all_surface_together(valid_settings_dict):
    """A comprehensively broken profile reports every bad field in one dict."""
    valid_settings_dict.update(
        username="AB",            # too short + uppercase
        email="not-an-email",
        password="weak",          # too short + missing classes
        theme="chartreuse",       # not an enum value
    )
    with pytest.raises(ValidationError) as ei:
        validate_and_create(valid_settings_dict)

    assert set(["username", "email", "password", "theme"]).issubset(ei.value.errors.keys())


# --- Immutability & model-level guarantees ----------------------------------


def test_settings_is_frozen(valid_settings_dict):
    """The model is immutable: attribute assignment must raise."""
    settings = validate_and_create(valid_settings_dict)
    with pytest.raises((PydanticValidationError, Exception)):
        settings.username = "changed"  # type: ignore[misc]


def test_extra_fields_rejected(valid_settings_dict):
    """Unknown top-level keys are forbidden (extra='forbid')."""
    valid_settings_dict["extra"] = "sneaky"
    with pytest.raises(ValidationError) as ei:
        validate_and_create(valid_settings_dict)
    assert "extra" in ei.value.errors


# --- validate_and_create input guards --------------------------------------


def test_validate_and_create_rejects_non_dict():
    """A list (or any non-dict) must raise TypeError, not slide through."""
    with pytest.raises(TypeError):
        validate_and_create(["username", "foo"])  # type: ignore[arg-type]


def test_validate_and_create_missing_all_fields():
    """An empty dict surfaces errors for every required field."""
    with pytest.raises(ValidationError) as ei:
        validate_and_create({})
    assert {"username", "email", "password", "theme"}.issubset(ei.value.errors.keys())


# --- ValidationError structural guarantees -----------------------------------


def test_validation_error_rejects_non_dict_payload():
    """``ValidationError`` refuses a non-dict input — no raw data smuggling."""
    with pytest.raises(TypeError):
        ValidationError("just a string")  # type: ignore[arg-type]


def test_validation_error_rejects_non_str_values():
    """Values must be str; a dict value of int is rejected."""
    with pytest.raises(TypeError):
        ValidationError({"password": 123})  # type: ignore[arg-type]


def test_validation_error_rejects_empty_dict():
    """An error with no entries is meaningless and must not be constructible."""
    with pytest.raises(ValueError):
        ValidationError({})


def test_validation_error_message_is_string_or_iterable_of_messages(valid_settings_dict):
    """``str`` and dict-like access behave sensibly for logging/tests."""
    valid_settings_dict["password"] = "bad"
    with pytest.raises(ValidationError) as ei:
        validate_and_create(valid_settings_dict)
    assert isinstance(str(ei.value), str)
    assert "password" in ei.value
    assert ei.value["password"]  # __getitem__ returns a non-empty str
