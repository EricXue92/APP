from app.i18n import t


def test_translate_zh_hans():
    assert t("auth.invalid_credentials", "zh-Hans") == "用户名或密码错误"


def test_translate_zh_hant():
    assert t("auth.invalid_credentials", "zh-Hant") == "用戶名或密碼錯誤"


def test_translate_en():
    assert t("auth.invalid_credentials", "en") == "Invalid credentials"


def test_translate_fallback_to_en():
    assert t("auth.invalid_credentials", "ja") == "Invalid credentials"


def test_translate_missing_key():
    result = t("nonexistent.key", "en")
    assert result == "nonexistent.key"
