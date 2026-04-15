import pytest

from app.services.word_filter import contains_blocked_word, load_blocked_words


def test_load_blocked_words():
    words = load_blocked_words()
    assert isinstance(words, list)
    assert len(words) > 0


def test_contains_blocked_word_match():
    assert contains_blocked_word("you are 傻逼") is True


def test_contains_blocked_word_clean():
    assert contains_blocked_word("nice game today") is False


def test_contains_blocked_word_empty():
    assert contains_blocked_word("") is False


def test_contains_blocked_word_case_insensitive():
    assert contains_blocked_word("FUCK YOU buddy") is True
