"""Serialization helpers shared by CLI, API, and MCP adapters."""

from datetime import date, datetime
from decimal import Decimal


def json_default(obj):
    """JSON serializer for non-standard types."""
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    return str(obj)
