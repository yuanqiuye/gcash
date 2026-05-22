"""Domain exceptions for gcash.

Adapters such as Click, FastAPI, and MCP should translate these into their
own error formats. Core service code should not terminate the process.
"""


class GCashError(Exception):
    """Base class for expected gcash operational errors."""


class ValidationError(GCashError, ValueError):
    """Raised when user-supplied bookkeeping data is invalid."""


class BookLockedError(GCashError):
    """Raised when a GnuCash lock file indicates the book is in use."""


class MutationLockError(GCashError):
    """Raised when another gcash process is already mutating the book."""


class BackupError(GCashError):
    """Raised when a required backup or restore safety step fails."""
