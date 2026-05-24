from decimal import Decimal

import pytest

from gnucash_cli.exceptions import ValidationError
from gnucash_cli.services.accounts import create_account, list_accounts
from gnucash_cli.services.transactions import build_split


class _Commodity:
    def __init__(self, mnemonic="TWD"):
        self.mnemonic = mnemonic


class _Account:
    def __init__(
        self,
        *,
        guid,
        fullname,
        name=None,
        account_type="ASSET",
        commodity=None,
        placeholder=False,
        children=None,
        description="",
    ):
        self.guid = guid
        self.fullname = fullname
        self.name = name or fullname.rsplit(":", 1)[-1]
        self.type = account_type
        self.commodity = commodity or _Commodity()
        self.placeholder = placeholder
        self.children = children or []
        self.description = description

    def get_balance(self):
        return Decimal("0")


class _Accounts:
    def __init__(self, accounts):
        self._accounts = list(accounts)

    def __iter__(self):
        return iter(self._accounts)

    def __call__(self, *, fullname=None, **_kwargs):
        if fullname is None:
            raise TypeError("fullname is required")
        for account in self._accounts:
            if account.fullname == fullname:
                return account
        raise LookupError(fullname)


class _Commodities:
    def __init__(self, commodity):
        self._commodity = commodity

    def get(self, mnemonic, **_kwargs):
        if mnemonic == self._commodity.mnemonic:
            return self._commodity
        raise LookupError(mnemonic)


class _Book:
    def __init__(self, accounts, commodity=None):
        commodity = commodity or _Commodity()
        self.accounts = _Accounts(accounts)
        self.commodities = _Commodities(commodity)
        self.root_account = _Account(guid="root-guid", fullname="", name="Root", commodity=commodity)
        self.saved = False

    def save(self):
        self.saved = True


class _Context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, *_args):
        return None


def test_list_accounts_returns_stable_account_ids(monkeypatch):
    account = _Account(guid="account-guid-1", fullname="Assets:Cash")
    book = _Book([account])

    monkeypatch.setattr("gnucash_cli.services.accounts.readonly_book", lambda _book_path: _Context(book))

    result = list_accounts("book.gnucash")

    assert result["accounts"][0]["id"] == "account-guid-1"
    assert result["accounts"][0]["guid"] == "account-guid-1"
    assert result["accounts"][0]["fullname"] == "Assets:Cash"


def test_build_split_uses_account_id_even_if_account_name_is_stale():
    account = _Account(guid="bank-guid", fullname="資產:C0銀行:中信薪資戶")
    book = _Book([account])
    tx_commodity = book.commodities.get(mnemonic="TWD")

    split = build_split(
        book,
        {"account_id": "bank-guid", "account": "中信薪資帳戶", "value": "50"},
        is_debit=False,
        tx_commodity=tx_commodity,
    )

    assert split["account"] is account
    assert split["value"] == Decimal("-50")


def test_build_split_rejects_unknown_account_id():
    book = _Book([_Account(guid="bank-guid", fullname="資產:C0銀行:中信薪資戶")])
    tx_commodity = book.commodities.get(mnemonic="TWD")

    with pytest.raises(ValidationError, match="Account id 'missing-guid' not found"):
        build_split(
            book,
            {"account_id": "missing-guid", "value": "50"},
            is_debit=False,
            tx_commodity=tx_commodity,
        )


def test_build_split_rejects_placeholder_account_id_with_child_suggestions():
    child = _Account(guid="child-guid", fullname="10_收入:零用錢:阿嬤", account_type="INCOME")
    parent = _Account(
        guid="parent-guid",
        fullname="10_收入:零用錢",
        account_type="INCOME",
        placeholder=True,
        children=[child],
    )
    book = _Book([parent, child])
    tx_commodity = book.commodities.get(mnemonic="TWD")

    with pytest.raises(ValidationError) as exc_info:
        build_split(
            book,
            {"account_id": "parent-guid", "value": "50"},
            is_debit=False,
            tx_commodity=tx_commodity,
        )

    message = str(exc_info.value)
    assert "placeholder" in message
    assert "10_收入:零用錢:阿嬤" in message
    assert "child-guid" in message


def test_build_split_resolves_unique_legacy_leaf_name():
    account = _Account(guid="post-guid", fullname="資產:C0銀行:郵局", name="郵局")
    book = _Book([account])
    tx_commodity = book.commodities.get(mnemonic="TWD")

    split = build_split(
        book,
        {"account": "郵局", "value": "50"},
        is_debit=False,
        tx_commodity=tx_commodity,
    )

    assert split["account"] is account


def test_build_split_resolves_unique_legacy_alias_name():
    account = _Account(guid="ctbc-guid", fullname="資產:C0銀行:中信薪資戶", name="中信薪資戶")
    book = _Book([account])
    tx_commodity = book.commodities.get(mnemonic="TWD")

    split = build_split(
        book,
        {"account": "中信薪資帳戶", "value": "50"},
        is_debit=False,
        tx_commodity=tx_commodity,
    )

    assert split["account"] is account


def test_build_split_rejects_ambiguous_legacy_leaf_name():
    cash = _Account(guid="cash-guid", fullname="Assets:Cash", name="Cash")
    petty_cash = _Account(guid="petty-guid", fullname="Assets:Petty Cash", name="Cash")
    book = _Book([cash, petty_cash])
    tx_commodity = book.commodities.get(mnemonic="TWD")

    with pytest.raises(ValidationError) as exc_info:
        build_split(
            book,
            {"account": "Cash", "value": "50"},
            is_debit=False,
            tx_commodity=tx_commodity,
        )

    message = str(exc_info.value)
    assert "ambiguous" in message
    assert "cash-guid" in message
    assert "petty-guid" in message


def test_build_split_suggests_siblings_for_missing_legacy_child():
    accounts = [
        _Account(guid="grandma-guid", fullname="10_收入:零用錢:阿嬤", account_type="INCOME"),
        _Account(guid="daily-guid", fullname="10_收入:零用錢:爸媽:日常", account_type="INCOME"),
        _Account(guid="aunt-guid", fullname="10_收入:零用錢:姑姑", account_type="INCOME"),
    ]
    book = _Book(accounts)
    tx_commodity = book.commodities.get(mnemonic="TWD")

    with pytest.raises(ValidationError) as exc_info:
        build_split(
            book,
            {"account": "10_收入:零用錢:姊姊", "value": "50"},
            is_debit=False,
            tx_commodity=tx_commodity,
        )

    message = str(exc_info.value)
    assert "10_收入:零用錢:阿嬤" in message
    assert "grandma-guid" in message
    assert "10_收入:零用錢:姑姑" in message


def test_create_account_accepts_parent_account_id(monkeypatch):
    parent = _Account(guid="parent-guid", fullname="Assets", name="Assets", placeholder=True)
    book = _Book([parent])
    created = {}

    def fake_account(**kwargs):
        created.update(kwargs)
        return _Account(
            guid="new-guid",
            fullname=f"{kwargs['parent'].fullname}:{kwargs['name']}",
            name=kwargs["name"],
            account_type=kwargs["type"],
            commodity=kwargs["commodity"],
            placeholder=kwargs["placeholder"],
            description=kwargs["description"],
        )

    monkeypatch.setattr("gnucash_cli.services.accounts.writable_book", lambda *_args, **_kwargs: _Context(book))
    monkeypatch.setattr("gnucash_cli.services.accounts.piecash.Account", fake_account)

    result = create_account(
        book_path="book.gnucash",
        name="Checking",
        account_type="BANK",
        parent_fullname=None,
        parent_account_id="parent-guid",
        currency_code="TWD",
        placeholder=False,
        description="Main bank",
        config={"default_currency": "TWD"},
        no_auto_backup=True,
    )

    assert created["parent"] is parent
    assert result["account"]["id"] == "new-guid"
    assert result["account"]["parent_id"] == "parent-guid"
