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
    "booking.not_found": {
        "zh-Hans": "约球未找到",
        "zh-Hant": "約球未找到",
        "en": "Booking not found",
    },
    "booking.not_open": {
        "zh-Hans": "该约球不在开放状态",
        "zh-Hant": "該約球不在開放狀態",
        "en": "Booking is not open for joining",
    },
    "booking.already_joined": {
        "zh-Hans": "你已经加入了这个约球",
        "zh-Hant": "你已經加入了這個約球",
        "en": "You have already joined this booking",
    },
    "booking.full": {
        "zh-Hans": "约球人数已满",
        "zh-Hant": "約球人數已滿",
        "en": "Booking is full",
    },
    "booking.ntrp_out_of_range": {
        "zh-Hans": "你的水平不在要求范围内",
        "zh-Hant": "你的水平不在要求範圍內",
        "en": "Your NTRP level is outside the required range",
    },
    "booking.gender_mismatch": {
        "zh-Hans": "该约球有性别要求",
        "zh-Hant": "該約球有性別要求",
        "en": "This booking has a gender requirement you don't meet",
    },
    "booking.credit_too_low": {
        "zh-Hans": "信用分不足，无法发起约球",
        "zh-Hant": "信用分不足，無法發起約球",
        "en": "Credit score too low to create a booking",
    },
    "booking.not_creator": {
        "zh-Hans": "只有发起人才能执行此操作",
        "zh-Hant": "只有發起人才能執行此操作",
        "en": "Only the booking creator can perform this action",
    },
    "booking.not_enough_participants": {
        "zh-Hans": "参与人数不足，无法确认",
        "zh-Hant": "參與人數不足，無法確認",
        "en": "Not enough participants to confirm",
    },
    "booking.cannot_complete": {
        "zh-Hans": "约球尚未到达可完成状态",
        "zh-Hant": "約球尚未到達可完成狀態",
        "en": "Booking cannot be completed yet",
    },
    "booking.already_cancelled": {
        "zh-Hans": "约球已被取消",
        "zh-Hant": "約球已被取消",
        "en": "Booking has already been cancelled",
    },
    "booking.play_date_past": {
        "zh-Hans": "打球日期必须在未来",
        "zh-Hant": "打球日期必須在未來",
        "en": "Play date must be in the future",
    },
    "court.not_found": {
        "zh-Hans": "球场未找到",
        "zh-Hant": "球場未找到",
        "en": "Court not found",
    },
    "court.not_approved": {
        "zh-Hans": "球场尚未审核通过",
        "zh-Hant": "球場尚未審核通過",
        "en": "Court is not yet approved",
    },
    "review.booking_not_completed": {
        "zh-Hans": "约球尚未完成",
        "zh-Hant": "約球尚未完成",
        "en": "Booking is not completed",
    },
    "review.not_participant": {
        "zh-Hans": "你不是该约球的参与者",
        "zh-Hant": "你不是該約球的參與者",
        "en": "You are not a participant in this booking",
    },
    "review.cannot_review_self": {
        "zh-Hans": "不能评价自己",
        "zh-Hant": "不能評價自己",
        "en": "Cannot review yourself",
    },
    "review.window_expired": {
        "zh-Hans": "评价时间已过",
        "zh-Hant": "評價時間已過",
        "en": "Review window has expired",
    },
    "review.already_submitted": {
        "zh-Hans": "你已经评价过此人",
        "zh-Hant": "你已經評價過此人",
        "en": "You have already reviewed this person",
    },
    "review.invalid_rating": {
        "zh-Hans": "评分必须在 1-5 之间",
        "zh-Hant": "評分必須在 1-5 之間",
        "en": "Rating must be between 1 and 5",
    },
}


def t(key: str, lang: str = "en") -> str:
    messages = _MESSAGES.get(key)
    if messages is None:
        return key
    return messages.get(lang, messages.get("en", key))
