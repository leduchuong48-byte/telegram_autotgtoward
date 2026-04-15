from __future__ import annotations


def normalize_chat_peer_key(raw_value) -> str:
    """Normalize chat identifiers to canonical positive peer key string."""
    if raw_value is None:
        return ""

    text = str(raw_value).strip()
    if not text:
        return ""

    if text.startswith("-100") and text[4:].isdigit():
        return text[4:]

    if text.startswith("-") and text[1:].isdigit():
        return text[1:]

    if text.isdigit():
        return text

    return text


def build_chat_id_aliases(raw_value) -> tuple[str, ...]:
    """Build compatible legacy/new aliases for chat ID matching."""
    canonical = normalize_chat_peer_key(raw_value)
    if not canonical:
        return tuple()

    aliases: list[str] = []

    def add(value: str) -> None:
        if value and value not in aliases:
            aliases.append(value)

    add(canonical)
    if canonical.isdigit():
        add(f"-{canonical}")
        add(f"-100{canonical}")
        add(f"100{canonical}")

    return tuple(aliases)
