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
        "zh-Hans": "信誉积分不足",
        "zh-Hant": "信譽積分不足",
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
        "zh-Hans": "信誉积分不足，无法发起约球",
        "zh-Hant": "信譽積分不足，無法發起約球",
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
    "block.cannot_block_self": {
        "zh-Hans": "不能拉黑自己",
        "zh-Hant": "不能封鎖自己",
        "en": "Cannot block yourself",
    },
    "block.already_blocked": {
        "zh-Hans": "已经拉黑了该用户",
        "zh-Hant": "已經封鎖了該用戶",
        "en": "User is already blocked",
    },
    "block.not_found": {
        "zh-Hans": "未找到拉黑记录",
        "zh-Hant": "未找到封鎖記錄",
        "en": "Block not found",
    },
    "block.user_not_found": {
        "zh-Hans": "用户不存在",
        "zh-Hant": "用戶不存在",
        "en": "User not found",
    },
    "report.cannot_report_self": {
        "zh-Hans": "不能举报自己",
        "zh-Hant": "不能檢舉自己",
        "en": "Cannot report yourself",
    },
    "report.already_reported": {
        "zh-Hans": "你已经举报过了",
        "zh-Hant": "你已經檢舉過了",
        "en": "You have already reported this",
    },
    "report.target_not_found": {
        "zh-Hans": "举报对象未找到",
        "zh-Hant": "檢舉對象未找到",
        "en": "Report target not found",
    },
    "report.review_already_hidden": {
        "zh-Hans": "该评价已被隐藏",
        "zh-Hant": "該評價已被隱藏",
        "en": "This review is already hidden",
    },
    "report.not_found": {
        "zh-Hans": "举报未找到",
        "zh-Hant": "檢舉未找到",
        "en": "Report not found",
    },
    "report.already_resolved": {
        "zh-Hans": "举报已处理",
        "zh-Hant": "檢舉已處理",
        "en": "Report has already been resolved",
    },
    "report.invalid_resolution_for_target": {
        "zh-Hans": "该处理方式不适用于此举报类型",
        "zh-Hant": "該處理方式不適用於此檢舉類型",
        "en": "This resolution is not valid for this report type",
    },
    "auth.account_suspended": {
        "zh-Hans": "账号已被停用",
        "zh-Hant": "帳號已被停用",
        "en": "Account has been suspended",
    },
    "common.admin_required": {
        "zh-Hans": "需要管理员权限",
        "zh-Hant": "需要管理員權限",
        "en": "Admin access required",
    },
    "block.user_blocked": {
        "zh-Hans": "操作被拒绝",
        "zh-Hant": "操作被拒絕",
        "en": "Action not allowed",
    },
    "follow.cannot_follow_self": {
        "zh-Hans": "不能关注自己",
        "zh-Hant": "不能關注自己",
        "en": "Cannot follow yourself",
    },
    "follow.already_following": {
        "zh-Hans": "已经关注了该用户",
        "zh-Hant": "已經關注了該用戶",
        "en": "Already following this user",
    },
    "follow.not_found": {
        "zh-Hans": "未找到关注记录",
        "zh-Hant": "未找到關注記錄",
        "en": "Follow not found",
    },
    "follow.user_not_found": {
        "zh-Hans": "用户不存在",
        "zh-Hant": "用戶不存在",
        "en": "User not found",
    },
    "follow.blocked": {
        "zh-Hans": "操作被拒绝",
        "zh-Hant": "操作被拒絕",
        "en": "Action not allowed",
    },
    "assistant.rate_limit": {
        "zh-Hans": "请求过于频繁，请稍后再试",
        "zh-Hant": "請求過於頻繁，請稍後再試",
        "en": "Too many requests, please try again later",
    },
    "assistant.llm_error": {
        "zh-Hans": "AI 服务暂时不可用",
        "zh-Hant": "AI 服務暫時不可用",
        "en": "AI service temporarily unavailable",
    },
    "matching.preference_exists": {
        "zh-Hans": "匹配偏好已存在",
        "zh-Hant": "配對偏好已存在",
        "en": "Match preference already exists",
    },
    "matching.preference_not_found": {
        "zh-Hans": "匹配偏好未找到",
        "zh-Hant": "配對偏好未找到",
        "en": "Match preference not found",
    },
    "matching.preference_inactive": {
        "zh-Hans": "匹配功能未激活",
        "zh-Hant": "配對功能未啟用",
        "en": "Matching is not active",
    },
    "matching.proposal_daily_cap": {
        "zh-Hans": "今日发送配对请求已达上限",
        "zh-Hant": "今日發送配對請求已達上限",
        "en": "Daily proposal limit reached",
    },
    "matching.cannot_propose_self": {
        "zh-Hans": "不能向自己发送配对请求",
        "zh-Hant": "不能向自己發送配對請求",
        "en": "Cannot send a proposal to yourself",
    },
    "matching.proposal_not_found": {
        "zh-Hans": "配对请求未找到",
        "zh-Hant": "配對請求未找到",
        "en": "Proposal not found",
    },
    "matching.proposal_not_pending": {
        "zh-Hans": "配对请求已处理",
        "zh-Hant": "配對請求已處理",
        "en": "Proposal is no longer pending",
    },
    "matching.proposal_not_target": {
        "zh-Hans": "只有接收方才能回应",
        "zh-Hant": "只有接收方才能回應",
        "en": "Only the proposal target can respond",
    },
    "matching.duplicate_pending": {
        "zh-Hans": "你已向该用户发送了配对请求",
        "zh-Hant": "你已向該用戶發送了配對請求",
        "en": "You already have a pending proposal to this user",
    },
    "matching.proposer_suspended": {
        "zh-Hans": "对方账号已被停用",
        "zh-Hant": "對方帳號已被停用",
        "en": "Proposer's account has been suspended",
    },
    "matching.target_not_found": {
        "zh-Hans": "目标用户不存在",
        "zh-Hant": "目標用戶不存在",
        "en": "Target user not found",
    },
    "weather.typhoon": {
        "zh-Hans": "台风警告生效，建议取消",
        "zh-Hant": "颱風警告生效，建議取消",
        "en": "Typhoon warning active, consider cancelling",
    },
    "weather.rainstorm": {
        "zh-Hans": "暴雨警告生效，建议取消",
        "zh-Hant": "暴雨警告生效，建議取消",
        "en": "Heavy rainstorm warning active, consider cancelling",
    },
    "weather.rain_high": {
        "zh-Hans": "降雨概率极高，可免责取消",
        "zh-Hant": "降雨機率極高，可免責取消",
        "en": "Very high chance of rain, free cancellation available",
    },
    "weather.heat_extreme": {
        "zh-Hans": "极端高温，建议取消",
        "zh-Hant": "極端高溫，建議取消",
        "en": "Extreme heat, consider cancelling",
    },
    "weather.heat_warning": {
        "zh-Hans": "高温预警，建议选择早晚时段",
        "zh-Hant": "高溫預警，建議選擇早晚時段",
        "en": "High temperature warning, consider early or late hours",
    },
    "weather.uv_warning": {
        "zh-Hans": "紫外线强烈，请注意防晒",
        "zh-Hant": "紫外線強烈，請注意防曬",
        "en": "Strong UV, please wear sunscreen",
    },
    "weather.rain_possible": {
        "zh-Hans": "有降雨可能，建议携带雨具",
        "zh-Hant": "有降雨可能，建議攜帶雨具",
        "en": "Possible rain, consider bringing an umbrella",
    },
    "weather.court_no_coordinates": {
        "zh-Hans": "该球场缺少坐标信息",
        "zh-Hant": "該球場缺少坐標資訊",
        "en": "This court has no location coordinates",
    },
    "weather.date_out_of_range": {
        "zh-Hans": "日期必须在今天到未来7天之间",
        "zh-Hant": "日期必須在今天到未來7天之間",
        "en": "Date must be between today and 7 days from now",
    },
    "weather.service_unavailable": {
        "zh-Hans": "天气服务暂时不可用",
        "zh-Hant": "天氣服務暫時不可用",
        "en": "Weather service temporarily unavailable",
    },
    "chat.room_not_found": {
        "zh-Hans": "聊天室不存在",
        "zh-Hant": "聊天室不存在",
        "en": "Chat room not found",
    },
    "chat.not_participant": {
        "zh-Hans": "你不是该聊天室的成员",
        "zh-Hant": "你不是該聊天室的成員",
        "en": "You are not a participant of this chat room",
    },
    "chat.room_readonly": {
        "zh-Hans": "该聊天室已设为只读",
        "zh-Hant": "該聊天室已設為唯讀",
        "en": "This chat room is read-only",
    },
    "chat.blocked_word": {
        "zh-Hans": "消息包含不当内容",
        "zh-Hant": "訊息包含不當內容",
        "en": "Message contains inappropriate content",
    },
    "event.not_found": {
        "zh-Hans": "赛事未找到",
        "zh-Hant": "賽事未找到",
        "en": "Event not found",
    },
    "event.not_creator": {
        "zh-Hans": "只有组织者才能执行此操作",
        "zh-Hant": "只有組織者才能執行此操作",
        "en": "Only the event organizer can perform this action",
    },
    "event.credit_too_low": {
        "zh-Hans": "信誉积分不足，无法创建赛事",
        "zh-Hant": "信譽積分不足，無法創建賽事",
        "en": "Credit score too low to create an event",
    },
    "event.not_open": {
        "zh-Hans": "赛事不在开放报名状态",
        "zh-Hant": "賽事不在開放報名狀態",
        "en": "Event is not open for registration",
    },
    "event.already_joined": {
        "zh-Hans": "你已经报名了这个赛事",
        "zh-Hant": "你已經報名了這個賽事",
        "en": "You have already joined this event",
    },
    "event.full": {
        "zh-Hans": "赛事报名人数已满",
        "zh-Hant": "賽事報名人數已滿",
        "en": "Event registration is full",
    },
    "event.ntrp_out_of_range": {
        "zh-Hans": "你的水平不在赛事要求范围内",
        "zh-Hant": "你的水平不在賽事要求範圍內",
        "en": "Your NTRP level is outside the event's required range",
    },
    "event.gender_mismatch": {
        "zh-Hans": "该赛事有性别要求",
        "zh-Hant": "該賽事有性別要求",
        "en": "This event has a gender requirement you don't meet",
    },
    "event.not_enough_participants": {
        "zh-Hans": "参赛人数不足，无法开始",
        "zh-Hant": "參賽人數不足，無法開始",
        "en": "Not enough participants to start the event",
    },
    "event.already_started": {
        "zh-Hans": "赛事已经开始",
        "zh-Hant": "賽事已經開始",
        "en": "Event has already started",
    },
    "event.not_in_progress": {
        "zh-Hans": "赛事不在进行中",
        "zh-Hant": "賽事不在進行中",
        "en": "Event is not in progress",
    },
    "event.cannot_modify": {
        "zh-Hans": "赛事当前状态不允许修改",
        "zh-Hant": "賽事當前狀態不允許修改",
        "en": "Event cannot be modified in its current status",
    },
    "event.match_not_found": {
        "zh-Hans": "比赛未找到",
        "zh-Hant": "比賽未找到",
        "en": "Match not found",
    },
    "event.not_match_player": {
        "zh-Hans": "你不是这场比赛的选手",
        "zh-Hant": "你不是這場比賽的選手",
        "en": "You are not a player in this match",
    },
    "event.match_not_ready": {
        "zh-Hans": "比赛尚未就绪（等待对手）",
        "zh-Hant": "比賽尚未就緒（等待對手）",
        "en": "Match is not ready (waiting for opponent)",
    },
    "event.score_already_submitted": {
        "zh-Hans": "比分已提交，等待确认",
        "zh-Hant": "比分已提交，等待確認",
        "en": "Score already submitted, awaiting confirmation",
    },
    "event.score_invalid": {
        "zh-Hans": "比分不合法",
        "zh-Hant": "比分不合法",
        "en": "Invalid score",
    },
    "event.match_not_submitted": {
        "zh-Hans": "比赛尚未提交比分",
        "zh-Hant": "比賽尚未提交比分",
        "en": "No score has been submitted for this match",
    },
    "event.cannot_confirm_own": {
        "zh-Hans": "不能确认自己提交的比分",
        "zh-Hant": "不能確認自己提交的比分",
        "en": "Cannot confirm your own score submission",
    },
    "event.not_registered": {
        "zh-Hans": "你未报名此赛事",
        "zh-Hant": "你未報名此賽事",
        "en": "You are not registered for this event",
    },
    "event.cannot_withdraw": {
        "zh-Hans": "赛事已开始，无法退出",
        "zh-Hant": "賽事已開始，無法退出",
        "en": "Cannot withdraw after the event has started",
    },
    "event.already_cancelled": {
        "zh-Hans": "赛事已被取消",
        "zh-Hant": "賽事已被取消",
        "en": "Event has already been cancelled",
    },
    "event.walkover_already_decided": {
        "zh-Hans": "该比赛已有结果",
        "zh-Hant": "該比賽已有結果",
        "en": "This match already has a result",
    },
    "event.not_participant": {
        "zh-Hans": "该用户不是赛事参与者",
        "zh-Hant": "該用戶不是賽事參與者",
        "en": "User is not a participant in this event",
    },
    "admin.user_already_suspended": {
        "zh-Hant": "該用戶已被停權",
        "zh-Hans": "该用户已被停权",
        "en": "User is already suspended",
    },
    "admin.user_not_suspended": {
        "zh-Hant": "該用戶未被停權",
        "zh-Hans": "该用户未被停权",
        "en": "User is not suspended",
    },
    "admin.cannot_change_own_role": {
        "zh-Hant": "無法修改自己的角色",
        "zh-Hans": "无法修改自己的角色",
        "en": "Cannot change your own role",
    },
    "admin.court_already_approved": {
        "zh-Hant": "該球場已通過審核",
        "zh-Hans": "该球场已通过审核",
        "en": "Court is already approved",
    },
    "admin.cannot_reject_approved_court": {
        "zh-Hant": "無法拒絕已審核通過的球場",
        "zh-Hans": "无法拒绝已审核通过的球场",
        "en": "Cannot reject an approved court",
    },
    "admin.booking_already_cancelled": {
        "zh-Hant": "該約球已取消",
        "zh-Hans": "该约球已取消",
        "en": "Booking is already cancelled",
    },
    "admin.event_already_cancelled": {
        "zh-Hant": "該賽事已取消",
        "zh-Hans": "该赛事已取消",
        "en": "Event is already cancelled",
    },
    # Push notification messages
    "push.booking_confirmed.title": {
        "zh-Hant": "訂場已確認",
        "zh-Hans": "订场已确认",
        "en": "Booking Confirmed",
    },
    "push.booking_confirmed.body": {
        "zh-Hant": "您的訂場已確認，請準時參加",
        "zh-Hans": "您的订场已确认，请准时参加",
        "en": "Your booking has been confirmed",
    },
    "push.booking_cancelled.title": {
        "zh-Hant": "訂場已取消",
        "zh-Hans": "订场已取消",
        "en": "Booking Cancelled",
    },
    "push.booking_cancelled.body": {
        "zh-Hant": "您參加的訂場已被取消",
        "zh-Hans": "您参加的订场已被取消",
        "en": "A booking you joined has been cancelled",
    },
    "push.match_proposal_received.title": {
        "zh-Hant": "收到配對邀請",
        "zh-Hans": "收到配对邀请",
        "en": "Match Proposal Received",
    },
    "push.match_proposal_received.body": {
        "zh-Hant": "有人邀請您一起打球",
        "zh-Hans": "有人邀请您一起打球",
        "en": "Someone wants to play tennis with you",
    },
    "push.event_match_ready.title": {
        "zh-Hant": "賽事對戰已就緒",
        "zh-Hans": "赛事对战已就绪",
        "en": "Event Match Ready",
    },
    "push.event_match_ready.body": {
        "zh-Hant": "您的下一場比賽已準備就緒",
        "zh-Hans": "您的下一场比赛已准备就绪",
        "en": "Your next match is ready",
    },
    "push.event_score_submitted.title": {
        "zh-Hant": "比分已提交",
        "zh-Hans": "比分已提交",
        "en": "Score Submitted",
    },
    "push.event_score_submitted.body": {
        "zh-Hant": "對手已提交比分，請確認",
        "zh-Hans": "对手已提交比分，请确认",
        "en": "Your opponent submitted a score, please confirm",
    },
    "push.event_score_disputed.title": {
        "zh-Hant": "比分有爭議",
        "zh-Hans": "比分有争议",
        "en": "Score Disputed",
    },
    "push.event_score_disputed.body": {
        "zh-Hant": "比分確認出現爭議，請聯繫管理員",
        "zh-Hans": "比分确认出现争议，请联系管理员",
        "en": "A score dispute needs attention",
    },
    "push.account_suspended.title": {
        "zh-Hant": "帳號已被停權",
        "zh-Hans": "账号已被停权",
        "en": "Account Suspended",
    },
    "push.account_suspended.body": {
        "zh-Hant": "您的帳號已被管理員停權",
        "zh-Hans": "您的账号已被管理员停权",
        "en": "Your account has been suspended by an administrator",
    },
    "push.new_chat_message.title": {
        "zh-Hant": "新訊息",
        "zh-Hans": "新消息",
        "en": "New Message",
    },
    "push.new_chat_message.body": {
        "zh-Hant": "您收到一條新訊息",
        "zh-Hans": "您收到一条新消息",
        "en": "You have a new message",
    },
    "invite.not_found": {
        "zh-Hans": "邀请未找到",
        "zh-Hant": "邀請未找到",
        "en": "Invite not found",
    },
    "invite.not_pending": {
        "zh-Hans": "邀请已处理",
        "zh-Hant": "邀請已處理",
        "en": "Invite is no longer pending",
    },
    "invite.cannot_invite_self": {
        "zh-Hans": "不能邀请自己",
        "zh-Hant": "不能邀請自己",
        "en": "Cannot invite yourself",
    },
    "invite.duplicate_pending": {
        "zh-Hans": "你已向该用户发送了邀请",
        "zh-Hant": "你已向該用戶發送了邀請",
        "en": "You already have a pending invite to this user",
    },
    "invite.invitee_not_found": {
        "zh-Hans": "被邀请人不存在",
        "zh-Hant": "被邀請人不存在",
        "en": "Invitee not found",
    },
    "invite.not_invitee": {
        "zh-Hans": "只有被邀请人才能回应",
        "zh-Hant": "只有被邀請人才能回應",
        "en": "Only the invitee can respond",
    },
    "invite.not_participant": {
        "zh-Hans": "你不是该邀请的参与方",
        "zh-Hant": "你不是該邀請的參與方",
        "en": "You are not a participant of this invite",
    },
    "push.booking_invite_received.title": {
        "zh-Hant": "收到約球邀請",
        "zh-Hans": "收到约球邀请",
        "en": "Booking Invite Received",
    },
    "push.booking_invite_received.body": {
        "zh-Hant": "有人邀請您一起打球",
        "zh-Hans": "有人邀请您一起打球",
        "en": "Someone invited you to play tennis",
    },
}


def t(key: str, lang: str = "en") -> str:
    messages = _MESSAGES.get(key)
    if messages is None:
        return key
    return messages.get(lang, messages.get("en", key))
