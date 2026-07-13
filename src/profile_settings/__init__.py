"""Public API for the profile-settings validation module.

Re-exports the handful of symbols the rest of the application should depend on.
Downstream code should never import from ``models`` / ``store`` / ``exceptions``
submodules directly — keeping a single import surface lets us refactor the
internals without breaking consumers.
"""

from .exceptions import ValidationError
from .models import ProfileSettings, Theme, validate_and_create
from .store import ProfileStore

__all__ = [
    "ValidationError",
    "ProfileSettings",
    "Theme",
    "validate_and_create",
    "ProfileStore",
]
