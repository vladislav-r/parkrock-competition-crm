MERCH_SIZES = frozenset({"XS", "S", "M", "L", "XL", "XXL", "3XL"})


def normalize_merch_size(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    if not normalized:
        return None
    if normalized not in MERCH_SIZES:
        raise ValueError("допустимые размеры: XS, S, M, L, XL, XXL, 3XL")
    return normalized
