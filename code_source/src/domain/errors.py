"""Business errors, independent of HTTP: raised by the services and the infrastructure adapters alike.

Each error carries a user-facing message and a machine `code` that the web pages test
(e.g. "already_paid"). The API maps each class to an HTTP status (api.responses).
"""

from __future__ import annotations

from typing import Optional


class ServiceError(Exception):
    code = "error"

    def __init__(self, message: str, code: Optional[str] = None) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFound(ServiceError):
    code = "not_found"


class InvalidRequest(ServiceError):
    """Input that passes the schema but breaks a business rule."""
    code = "invalid"


class Forbidden(ServiceError):
    """The request is valid but this action is not allowed (a sender address outside the club)."""
    code = "forbidden"


class Conflict(ServiceError):
    """The current state of the data forbids the action (paid, already linked, concurrent write)."""
    code = "conflict"


class StorageUnavailable(ServiceError):
    code = "unavailable"


class UpstreamUnavailable(ServiceError):
    """An outside service (HelloAsso) could not be reached or refused the call."""
    code = "upstream_unavailable"
