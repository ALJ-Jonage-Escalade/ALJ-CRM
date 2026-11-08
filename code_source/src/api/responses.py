"""HTTP helpers shared by the API routers."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Awaitable, Callable, Dict, Literal, Optional, Union

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from domain.errors import Conflict, InvalidRequest, NotFound, ServiceError, StorageUnavailable, UpstreamUnavailable

logger = logging.getLogger("alj")

# Member and competition data must not be kept in the browser's HTTP cache (personal data),
# so responses are never stored: the page keeps the last body in memory and sends
# If-None-Match itself, which makes an unchanged poll a cheap 304.
NO_STORE = "no-store"


def _etag_matches(header: str, etag: str) -> bool:
    candidates = [c.strip() for c in (header or "").split(",")]
    return "*" in candidates or etag in candidates or f"W/{etag}" in candidates


def json_with_etag(request: Request, payload: Any) -> Response:  # Any: any JSON-serializable value
    """JSON response with a strong ETag (hash of the body); 304 when the client already has it."""
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    etag = '"' + hashlib.sha256(body, usedforsecurity=False).hexdigest() + '"'
    headers = {"ETag": etag, "Cache-Control": NO_STORE}
    if _etag_matches(request.headers.get("if-none-match", ""), etag):
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


# Body of a write that has nothing else to return
SUCCESS: Dict[str, str] = {"status": "success"}


class ApiErrorBody(BaseModel):
    """Body of error(): what the frontend's API client turns into an ApiError."""
    status: Literal["error"]
    message: str
    code: Optional[str] = None


# Statuses a route over a @write or @storage service can answer (services/competitions/store.py): 409 when another
# device changed the data meanwhile, 503 when Firestore is unavailable
STORAGE_ERRORS = (409, 503)


def error_responses(*statuses: int) -> Dict[Union[int, str], Dict[str, Any]]:  # Any: FastAPI's `responses` format
    """`responses=` of a route answering error() with these statuses (documented in the OpenAPI contract)."""
    return {status: {"model": ApiErrorBody} for status in statuses}


def document_responses(model: type[BaseModel], *errors: int, status: int = 200) -> Dict[Union[int, str], Dict[str, Any]]:  # Any: as above
    """`responses=` of a route answering a stored document as it is, documented as `model`, plus the statuses of its
    error() answers. The route sets response_model=None: a response model would add the defaults and reorder the
    fields (the writes answer the same body as the reads)."""
    return {status: {"model": model}, **error_responses(*errors)}


def error(status: int, message: str, code: Optional[str] = None) -> JSONResponse:
    """Same error shape as the other API routes ({status, message}), plus a machine code."""
    body: Dict[str, str] = {"status": "error", "message": message}
    if code:
        body["code"] = code
    return JSONResponse(body, status_code=status)


GENERIC_ERROR = "Erreur interne du serveur (détails dans les journaux)."


def internal_error(e: Exception, where: str) -> str:
    """Logs the exception server-side; the client only gets a generic message
    (no paths, SQL or third-party details, notably on the public webhook)."""
    logger.error("[%s] %s: %s", where, type(e).__name__, e, exc_info=e)
    return GENERIC_ERROR


SERVICE_ERROR_STATUS = (
    (NotFound, 404),
    (InvalidRequest, 400),
    (Conflict, 409),
    (StorageUnavailable, 503),
    (UpstreamUnavailable, 502),
)


async def unhandled_error_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Innermost middleware: an exception no route handled gets the API's error shape (not Starlette's plain text),
    503 when Firestore failed, else 500; logged with its traceback, never shown. Being a middleware, its answer still
    goes through the other ones (security headers, replication of what was written)."""
    from infrastructure.firestore.client import FirestoreError
    try:
        return await call_next(request)
    except FirestoreError as e:
        return error(503, f"Base de données momentanément indisponible : {internal_error(e, request.url.path)}")
    except Exception as e:  # last resort for the whole app: every other failure answers the same 500
        return error(500, internal_error(e, request.url.path))


def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
    """Exception handler (registered on the app) turning service errors into HTTP errors."""
    status = next((s for cls, s in SERVICE_ERROR_STATUS if isinstance(exc, cls)), 500)
    return error(status, exc.message, exc.code)
