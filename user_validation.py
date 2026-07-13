"""Validate and save user credentials (email, username, password).

Stores users in a JSON file with salted + hashed passwords (PBKDF2-HMAC-SHA256).
Passwords are never stored in plaintext.
"""

import hashlib
import getpass
import json
import os
import re
import secrets
import sys

USERS_FILE = "users.json"
PBKDF2_ITERATIONS = 100_000
DK_LEN = 32  # bytes

# --- Validation rules ----------------------------------------------------

EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")

MIN_PASSWORD_LEN = 8
# at least one letter and one digit; allow any other printable chars
PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).+$")


class ValidationError(Exception):
    """Raised when a credential fails validation."""


def validate_email(email: str) -> str:
    email = (email or "").strip()
    if not email:
        raise ValidationError("Email is required.")
    if not EMAIL_RE.match(email):
        raise ValidationError("Invalid email format.")
    return email


def validate_username(username: str) -> str:
    username = (username or "").strip()
    if not username:
        raise ValidationError("Username is required.")
    if not USERNAME_RE.match(username):
        raise ValidationError(
            "Username must be 3-20 chars: letters, digits, or underscore only."
        )
    return username


def validate_password(password: str) -> str:
    if not password:
        raise ValidationError("Password is required.")
    if len(password) < MIN_PASSWORD_LEN:
        raise ValidationError(f"Password must be at least {MIN_PASSWORD_LEN} chars.")
    if " " in password:
        raise ValidationError("Password must not contain spaces.")
    if not PASSWORD_RE.match(password):
        raise ValidationError("Password must contain at least one letter and one digit.")
    return password


# --- Storage -------------------------------------------------------------

def load_users() -> dict:
    if not os.path.exists(USERS_FILE):
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"Could not read {USERS_FILE}: {exc}") from exc


def save_users(users: dict) -> None:
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


def hash_password(password: str) -> str:
    """Return an iterable-independent hash string: 'pbkdf2_sha256$iterations$salt_hex$hash_hex'."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS, dklen=DK_LEN)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${dk.hex()}"


# --- Main flow -----------------------------------------------------------

def register_user() -> None:
    print("=== User Registration ===")
    try:
        email = validate_email(input("Email: "))
        username = validate_username(input("Username: "))
        password = validate_password(getpass.getpass("Password: "))
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(1)

    users = load_users()
    norm_email = email.lower()
    if norm_email in users:
        print(f"Error: a user with email '{email}' already exists.")
        return
    for existing in users.values():
        if existing.get("username") == username:
            print(f"Error: username '{username}' is already taken.")
            return

    users[norm_email] = {
        "email": email,
        "username": username,
        "password_hash": hash_password(password),
    }
    save_users(users)
    print(f"User '{username}' registered successfully.")


if __name__ == "__main__":
    try:
        register_user()
    except ValidationError as exc:
        print(f"Validation error: {exc}")
        sys.exit(2)
    except RuntimeError as exc:
        print(f"Storage error: {exc}")
        sys.exit(3)
