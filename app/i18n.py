_MESSAGES: dict[str, dict[str, str]] = {
    "auth.invalid_credentials": {
        "zh-Hans": "用户名或密码错误",
        "zh-Hant": "用戶名或密碼錯誤",
        "en": "Invalid credentials",
    },
    "auth.user_not_found": {
        "zh-Hans": "用户不存在",
        "zh-Hant": "用戶不存在",
        "en": "User not found",
    },
    "auth.email_not_verified": {
        "zh-Hans": "邮箱未验证",
        "zh-Hant": "郵箱未驗證",
        "en": "Email not verified",
    },
    "auth.phone_code_invalid": {
        "zh-Hans": "验证码无效",
        "zh-Hant": "驗證碼無效",
        "en": "Invalid verification code",
    },
    "auth.account_disabled": {
        "zh-Hans": "账号已被禁用",
        "zh-Hant": "帳號已被停用",
        "en": "Account has been disabled",
    },
    "auth.provider_already_linked": {
        "zh-Hans": "该账号已被关联",
        "zh-Hant": "該帳號已被關聯",
        "en": "This account is already linked",
    },
    "user.credit_too_low": {
        "zh-Hans": "信用分不足",
        "zh-Hant": "信用分不足",
        "en": "Credit score too low",
    },
    "common.not_found": {
        "zh-Hans": "未找到",
        "zh-Hant": "未找到",
        "en": "Not found",
    },
    "common.forbidden": {
        "zh-Hans": "没有权限",
        "zh-Hant": "沒有權限",
        "en": "Forbidden",
    },
}


def t(key: str, lang: str = "en") -> str:
    messages = _MESSAGES.get(key)
    if messages is None:
        return key
    return messages.get(lang, messages.get("en", key))
