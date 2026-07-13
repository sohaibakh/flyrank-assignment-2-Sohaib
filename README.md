# flyrank-assignment-2-Sohaib

A robust, type-safe **ProfileSettings** validation module for a Python-based user
profile configuration manager. It validates `username`, `email`, `password`,
and `theme` fields with field-specific, structured errors, and persists the
validated settings to a local `config.json` in a thread-safe, atomic way.

## Requirements

- Python 3.11+ (developed against 3.13)
- pydantic v2 (`pydantic>=2.12,<3`) for the validation model
- pytest (`pytest>=8`) for the test suite

Install dependencies:

```bash
pip install -r requirements.txt
```

## Layout

```
src/profile_settings/
  __init__.py     # public API: ProfileSettings, Theme, ValidationError, ProfileStore
  exceptions.py   # custom ValidationError carrying a dict[str,str] of field errors
  models.py       # Theme enum + ProfileSettings pydantic model + validate_and_create
  store.py        # thread-safe, atomic JSON read/write of config.json
tests/
  conftest.py     # fixtures: temp ProfileStore + known-good settings dict
  test_models.py  # per-field validation: happy, boundary, failure, aggregation
  test_store.py   # persistence round-trip, atomicity, thread-safety, corruption
```

## Usage

```python
from profile_settings import ProfileStore, ValidationError, validate_and_create

raw = {
    "username": "sohaib123",
    "email": "sohaib@example.com",
    "password": "Str0ng!Pass",
    "theme": "dark",
}

try:
    settings = validate_and_create(raw)      # the ONLY place a raw dict is accepted
except ValidationError as exc:
    print(exc.errors)                          # e.g. {"password": "Too short", ...}
    raise

store = ProfileStore("config.json")
store.save(settings)     # atomic, thread-safe write
loaded = store.load()     # re-validates on read; None if no config exists
```

## Validation rules

| Field    | Rule                                                                 |
|----------|----------------------------------------------------------------------|
| username | lowercase alphanumeric, 3–20 chars                                   |
| email    | strict RFC 5322-aware regex (WHATWG HTML5 email spec)                |
| password | ≥8 chars with uppercase, lowercase, digit, and special char          |
| theme    | `Theme` enum: `light` / `dark` / `system`                           |

Errors are aggregated — every broken field is reported at once in a single
`ValidationError`, never just the first.

## Running the tests

```bash
python -m pytest -v
```
