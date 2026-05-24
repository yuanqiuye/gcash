"""Account lookup helpers shared by write paths."""

from __future__ import annotations

from difflib import SequenceMatcher

from gnucash_cli.exceptions import ValidationError


def account_id(account) -> str | None:
    """Return the stable GnuCash account GUID as an API identifier."""
    guid = getattr(account, "guid", None)
    if guid is None:
        return None
    text = str(guid).strip()
    return text or None


def account_is_placeholder(account) -> bool:
    value = getattr(account, "placeholder", False)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def describe_account(account) -> str:
    identifier = account_id(account)
    suffix = f" (id={identifier})" if identifier else ""
    return f"{getattr(account, 'fullname', '<unknown>')}{suffix}"


def iter_accounts(book) -> list:
    try:
        return list(book.accounts)
    except TypeError:
        return []


def normalize_account_path(value: str) -> str:
    parts = [part.strip() for part in value.strip().replace("：", ":").split(":")]
    return ":".join(part for part in parts if part)


def _alias_key(value: str) -> str:
    text = normalize_account_path(value)
    replacements = {
        "帳戶": "戶",
        "賬戶": "戶",
        "账户": "户",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _unique(accounts: list) -> list:
    seen = set()
    result = []
    for account in accounts:
        identifier = account_id(account) or getattr(account, "fullname", "")
        if identifier in seen:
            continue
        seen.add(identifier)
        result.append(account)
    return result


def _format_candidates(accounts: list, limit: int = 5) -> str:
    candidates = _unique(accounts)[:limit]
    if not candidates:
        return ""
    return "; ".join(describe_account(account) for account in candidates)


def _child_candidates(account) -> list:
    children = getattr(account, "children", None) or []
    try:
        return list(children)
    except TypeError:
        return []


def _ensure_postable(account) -> None:
    if not account_is_placeholder(account):
        return

    child_text = _format_candidates(_child_candidates(account))
    message = f"Account '{describe_account(account)}' is a placeholder and cannot be used in transactions."
    if child_text:
        message += f" Use a child account instead: {child_text}."
    raise ValidationError(message)


def _find_by_id(book, requested_id: str):
    target = requested_id.strip()
    for account in iter_accounts(book):
        if account_id(account) == target:
            return account
    raise ValidationError(
        f"Account id '{target}' not found. Call gnucash_list_accounts and use the returned account id."
    )


def _find_exact_fullname(book, requested_fullname: str):
    try:
        return book.accounts(fullname=requested_fullname)
    except Exception:
        for account in iter_accounts(book):
            if getattr(account, "fullname", None) == requested_fullname:
                return account
    return None


def _legacy_matches(book, requested_name: str) -> list:
    accounts = iter_accounts(book)
    normalized = normalize_account_path(requested_name)
    alias = _alias_key(requested_name)

    matches = []
    for account in accounts:
        fullname = normalize_account_path(getattr(account, "fullname", ""))
        name = normalize_account_path(getattr(account, "name", fullname.rsplit(":", 1)[-1]))
        if fullname == normalized or name == normalized:
            matches.append(account)
            continue
        if fullname.endswith(f":{normalized}"):
            matches.append(account)
            continue
        if _alias_key(name) == alias or _alias_key(fullname).endswith(f":{alias}"):
            matches.append(account)

    return _unique(matches)


def _suggestions(book, requested_name: str) -> list:
    accounts = iter_accounts(book)
    normalized = normalize_account_path(requested_name)
    parent = normalized.rsplit(":", 1)[0] if ":" in normalized else None

    if parent:
        siblings = [
            account
            for account in accounts
            if normalize_account_path(getattr(account, "fullname", "")).startswith(f"{parent}:")
            and normalize_account_path(getattr(account, "fullname", "")) != normalized
            and not account_is_placeholder(account)
        ]
        if siblings:
            return _unique(siblings)

    ranked = sorted(
        accounts,
        key=lambda account: max(
            SequenceMatcher(None, normalized, normalize_account_path(getattr(account, "fullname", ""))).ratio(),
            SequenceMatcher(None, normalized, normalize_account_path(getattr(account, "name", ""))).ratio(),
        ),
        reverse=True,
    )
    return [account for account in ranked if not account_is_placeholder(account)][:5]


def resolve_account(
    book,
    *,
    account_id_value: str | None = None,
    account_fullname: str | None = None,
    require_postable: bool = False,
):
    """Resolve an account by stable id first, then by legacy name/fullname."""
    if account_id_value:
        account = _find_by_id(book, account_id_value)
        if require_postable:
            _ensure_postable(account)
        return account

    if not account_fullname:
        raise ValidationError("Account id or account fullname is required.")

    requested = normalize_account_path(account_fullname)
    account = _find_exact_fullname(book, requested)
    if account is not None:
        if require_postable:
            _ensure_postable(account)
        return account

    matches = _legacy_matches(book, requested)
    if len(matches) == 1:
        account = matches[0]
        if require_postable:
            _ensure_postable(account)
        return account

    if len(matches) > 1:
        raise ValidationError(
            f"Account '{account_fullname}' is ambiguous. Use account_id from gnucash_list_accounts. "
            f"Candidates: {_format_candidates(matches)}."
        )

    suggestions = _format_candidates(_suggestions(book, requested))
    message = f"Account '{account_fullname}' not found. Use account_id from gnucash_list_accounts."
    if suggestions:
        message += f" Did you mean: {suggestions}?"
    raise ValidationError(message)
