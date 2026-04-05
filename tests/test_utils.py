import pytest
import json
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch

import click

from gnucash_cli.utils import output_result, _json_default
from gnucash_cli.commands.transactions import _parse_split_spec

def test_json_default():
    """Test JSON serializer for non-standard types."""
    assert _json_default(Decimal("10.5")) == 10.5
    
    d = date(2026, 4, 1)
    assert _json_default(d) == "2026-04-01"
    
    dt = datetime(2026, 4, 1, 10, 30)
    assert _json_default(dt) == "2026-04-01T10:30:00"
    
    # Unknown type should fallback to string
    class Dummy:
        def __str__(self):
            return "dummy"
    assert _json_default(Dummy()) == "dummy"

def test_output_result_json(capsys):
    """Test output_result JSON formatting."""
    data = {"amount": Decimal("100.50"), "date": date(2026, 4, 1)}
    
    output_result(data, fmt="json")
    captured = capsys.readouterr()
    
    parsed = json.loads(captured.out)
    assert parsed["amount"] == 100.5
    assert parsed["date"] == "2026-04-01"

def test_output_result_table():
    """Test output_result uses table_builder when format is not json."""
    data = [{"id": 1}]
    table_builder = MagicMock()
    
    output_result(data, fmt="table", table_builder=table_builder)
    
    table_builder.assert_called_once_with(data)

def test_parse_split_spec_simple():
    """Test _parse_split_spec simple format: 'Account 100'"""
    spec = "Assets:Cash 100.50"
    res = _parse_split_spec(spec)
    
    assert res["account_fullname"] == "Assets:Cash"
    assert res["value"] == Decimal("100.50")
    assert res["currency"] is None
    assert res["quantity"] is None
    
    # Test negative
    res = _parse_split_spec("Expenses:Food -50")
    assert res["account_fullname"] == "Expenses:Food"
    assert res["value"] == Decimal("-50")

def test_parse_split_spec_with_currency():
    """Test _parse_split_spec format: 'Account 100 USD'"""
    spec = "Assets:Cash 100.50 USD"
    res = _parse_split_spec(spec)
    
    assert res["account_fullname"] == "Assets:Cash"
    assert res["value"] == Decimal("100.50")
    assert res["currency"] == "USD"
    assert res["quantity"] is None

def test_parse_split_spec_multi_currency():
    """Test _parse_split_spec format: 'Account 100 USD 30'"""
    spec = "Assets:Cash 930 TWD 30.0"
    res = _parse_split_spec(spec)
    
    assert res["account_fullname"] == "Assets:Cash"
    assert res["value"] == Decimal("930")
    assert res["currency"] == "TWD"
    assert res["quantity"] == Decimal("30.0")

def test_parse_split_spec_with_spaces():
    """Test _parse_split_spec handles account names with spaces."""
    spec = "Assets:My Cash Account 100"
    res = _parse_split_spec(spec)
    
    assert res["account_fullname"] == "Assets:My Cash Account"
    assert res["value"] == Decimal("100")
    
def test_parse_split_spec_invalid():
    """Test _parse_split_spec raises error for invalid input."""
    with pytest.raises(ValueError):
        _parse_split_spec("InvalidSpec")
        
    with pytest.raises(ValueError):
        _parse_split_spec("Account string_amount")
