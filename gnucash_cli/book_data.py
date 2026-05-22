"""Book data mapping helpers."""


def build_account_tree_data(book) -> list[dict]:
    """Build account data list from a piecash book."""
    accounts = []
    for acc in book.accounts:
        children_names = [c.fullname for c in acc.children] if acc.children else []
        try:
            balance = str(acc.get_balance())
        except Exception:
            balance = "0"

        accounts.append({
            "fullname": acc.fullname,
            "name": acc.name,
            "type": acc.type,
            "currency": acc.commodity.mnemonic if acc.commodity else None,
            "placeholder": bool(acc.placeholder),
            "balance": balance,
            "description": acc.description or "",
            "children": children_names,
        })
    return accounts
