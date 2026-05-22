"""Shared API-key and bind-host policy helpers."""

from __future__ import annotations

import hmac
import os
from typing import Mapping


def is_loopback_host(host: str) -> bool:
    return host in {"127.0.0.1", "localhost", "::1"}


def resolve_api_key(config: dict | None = None) -> str | None:
    effective_config = config or {}
    return os.environ.get("GNUCASH_API_KEY") or effective_config.get("api_key")


def resolve_mcp_http_api_key(config: dict | None = None) -> str | None:
    effective_config = config or {}
    return (
        os.environ.get("GNUCASH_MCP_HTTP_API_KEY")
        or os.environ.get("GNUCASH_API_KEY")
        or effective_config.get("mcp_http_api_key")
        or effective_config.get("api_key")
    )


def has_exposed_bind_api_key(config: dict | None = None) -> bool:
    return bool(resolve_mcp_http_api_key(config) or resolve_api_key(config))


def is_api_key_authorized(
    *,
    expected_key: str | None,
    x_api_key: str | None = None,
    authorization: str | None = None,
) -> bool:
    if not expected_key:
        return True

    bearer = ""
    if authorization:
        bearer = authorization.removeprefix("Bearer ").strip()

    return (
        bool(x_api_key) and hmac.compare_digest(x_api_key, expected_key)
    ) or (
        bool(bearer) and hmac.compare_digest(bearer, expected_key)
    )


def is_asgi_scope_authorized(scope, expected_key: str | None) -> bool:
    headers = {key.lower(): value for key, value in scope.get("headers", [])}
    return is_api_key_authorized(
        expected_key=expected_key,
        x_api_key=_decode_header(headers, b"x-api-key"),
        authorization=_decode_header(headers, b"authorization"),
    )


def is_headers_authorized(headers: Mapping[str, str], expected_key: str | None) -> bool:
    lower_headers = {key.lower(): value for key, value in headers.items()}
    return is_api_key_authorized(
        expected_key=expected_key,
        x_api_key=lower_headers.get("x-api-key"),
        authorization=lower_headers.get("authorization"),
    )


def _decode_header(headers: dict[bytes, bytes], key: bytes) -> str | None:
    value = headers.get(key)
    if value is None:
        return None
    return value.decode("utf-8")
