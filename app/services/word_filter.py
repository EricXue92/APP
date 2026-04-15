from pathlib import Path

_BLOCKED_WORDS: list[str] = []


def load_blocked_words() -> list[str]:
    global _BLOCKED_WORDS
    if _BLOCKED_WORDS:
        return _BLOCKED_WORDS
    words_file = Path(__file__).parent.parent / "data" / "blocked_words.txt"
    if words_file.exists():
        _BLOCKED_WORDS = [
            line.strip().lower()
            for line in words_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    return _BLOCKED_WORDS


def contains_blocked_word(content: str) -> bool:
    if not content:
        return False
    words = load_blocked_words()
    content_lower = content.lower()
    return any(word in content_lower for word in words)
