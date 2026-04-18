# Let's Tennis - 网球约球 iOS App 设计文档

## 概述

**Let's Tennis** 是一款面向网球爱好者的 iOS 约球应用，帮助水平相近的球友找到对手、约定球场、组织比赛。首期上线城市为香港，后续扩展至北京、上海、杭州、广州、深圳、武汉、成都、天津、沈阳。

**技术栈：** SwiftUI (iOS) + FastAPI (Python 后端) + PostgreSQL + Redis

**多语言：** 简体中文、繁体中文、英文

---

## 1. 用户系统

### 1.1 登录方式（5种）

- 手机号 + 验证码（MVP 阶段：验证码 "000000" 始终有效）
- **Sign in with Apple**（Apple 登录，iOS 必备——App Store 审核要求：提供第三方登录时必须同时提供 Apple 登录）
- 微信一键登录（已定义 schema 和 AuthProvider 枚举，路由尚未实现）
- 用户名 + 密码（需邮箱认证激活）
- Google 账号登录（已定义 schema 和 AuthProvider 枚举，路由尚未实现）

**登录持久化：** JWT Token（access + refresh）存入 iOS Keychain，自动刷新。access token 有效期 30 分钟，refresh token 有效期 30 天。用户无需重复登录，除非主动退出。

**多认证方式绑定：** 通过 `UserAuth` 模型支持，以 `(provider, provider_user_id)` 为唯一键，一个用户可绑定多种登录方式。`AuthProvider` 枚举：PHONE, WECHAT, GOOGLE, USERNAME, APPLE。

### 1.2 注册流程

1. 选择登录方式并完成认证
2. 基本资料：昵称、头像、**性别（必填）**、所在城市
3. 网球水平设置：**NTRP 等级指南**（参考 `GET /api/v1/ntrp/levels`，提供 1.5-7.0 各等级三语详细描述）**或 直接输入**（如 3.0+、3.5-、2.5、4.0）
4. 完善资料（可选）：常去球场、偏好时间、打球年限（years_playing）、个人简介（bio）、语言偏好

**NTRP 等级支持 +/- 修饰符：** 如 `3.5+`、`4.0-`，系统内部通过 `_ntrp_to_float()` 将其转换为浮点数（±0.05）用于范围比较。`ntrp_label` 为展示用的标签，由 `generate_ntrp_label()` 自动生成。

### 1.3 NTRP 等级指南

`GET /api/v1/ntrp/levels` 返回完整的 NTRP 等级指南，支持三语（zh-Hans、zh-Hant、en）。

- 覆盖 1.5 到 7.0 所有级别
- 按分组展示（初学者、初级、中级、中高级、高级、专业）
- 每个级别附带 3-4 条技能描述
- 帮助用户在注册时准确自评水平

### 1.4 个人主页

- 头像 + 昵称 + 性别 + 城市
- **水平标签：** 如 "3.5 中级" / "3.5+" / "4.0 中高级"（由 `ntrp_label` 提供）
- 信誉积分 + 赴约率
- 理想球友徽章（`is_ideal_player` 字段）
- 打球统计（场次、常去球场、最近活跃）
- 收到的评价
- 隐私控制：可设置信息 公开 / 仅好友可见 / 隐藏

### 1.5 用户搜索

`GET /api/v1/users/search` 提供强大的用户搜索功能：

**搜索过滤条件：**

- `keyword` — 关键词搜索（匹配昵称）
- `city` — 城市筛选
- `gender` — 性别筛选
- `min_ntrp` / `max_ntrp` — NTRP 水平范围
- `court_id` + `radius_km` — 球场附近搜索（基于 Haversine 公式计算地理距离）
- `ideal_only` — 仅显示理想球友

**搜索特性：**

- 自动排除被屏蔽的用户
- 理想球友优先排序
- 返回关注状态（`is_following`）和最后活跃时间
- 分页支持（offset / limit）

### 1.6 用户统计与日历

- `GET /api/v1/users/{user_id}/stats` — 打球统计：总场次、本月场次、单打/双打分别计数、常去球场 Top3、最常搭档
- `GET /api/v1/users/{user_id}/calendar` — 月度日历视图：返回指定年月的比赛日期列表

---

## 2. 约球功能

### 2.1 模式一：发布约球帖

发起人填写：

- 类型：单打 / 双打
- 日期 + 时间段
- 球场（地图搜索选择）
- 要求水平范围（如 3.0-4.0）
- 性别要求：仅男 / 仅女 / 不限
- 费用说明（AA 或免费）
- 备注（自带球、需要教练等）

**人数上限自动计算：** 单打 = 2 人，双打 = 4 人。

**发起约球要求：** 信誉积分 ≥ 60。

**流程：** 发布 → 符合条件的用户看到 → 报名（校验 NTRP、性别、屏蔽、容量） → 发起人确认（需至少 2 人接受） → 约球成立（**自动创建聊天会话**） → 聊天沟通细节

**双打：** 需凑齐 2-4 人，发起人可自带搭档。

**约球列表排序：** 理想球友发布的约球帖优先展示。

### 2.2 模式二：智能匹配

用户设置偏好（`MatchPreference`，每用户一份）：

- 可用时间段（`MatchTimeSlot` — 星期几 + 开始/结束时间，需为整点或半点）
- 偏好球场（`MatchPreferenceCourt` — 关联多个球场）/ 可接受距离（`max_distance_km`）
- 单打 / 双打 / 都行
- 对手水平范围（`min_ntrp` / `max_ntrp`）
- 性别偏好
- 费用默认 AA

**匹配权重（算法评分）：**

| 维度      | 权重 | 说明           |
| --------- | ---- | -------------- |
| NTRP 水平 | 35%  | ±0.5 优先      |
| 时间重叠  | 25%  | 可用时间段匹配 |
| 地理距离  | 20%  | 偏好球场距离近 |
| 信誉积分  | 10%  | 信誉积分高优先 |
| 性别匹配  | 5%   | 性别偏好匹配   |
| 理想球友  | 5%   | 理想球友加成   |

**被动匹配：** 创建/更新偏好或激活偏好时，系统自动触发 `trigger_passive_matching()`，向匹配度 ≥ 60 分的用户发送 `MATCH_SUGGESTION` 通知（同一对用户 7 天冷却期）。

**候选人列表：** `GET /api/v1/matching/candidates` 返回评分排序的候选球友列表。

**推荐约球帖：** `GET /api/v1/matching/bookings` 根据偏好推荐现有的开放约球帖。

### 2.3 模式三：匹配提案（Match Proposal）

用户可向匹配到的候选人发送约球提案：

**流程：**

1. 发送提案（`POST /api/v1/matching/proposals`）：指定球场、类型、日期时间、可选留言
2. 对方收到 `MATCH_PROPOSAL_RECEIVED` 通知
3. 对方确认（`PATCH /api/v1/matching/proposals/{id}`）→ **自动创建约球 + 聊天会话**
4. 对方拒绝 → 通知发起人

**规则：**

- 每用户每天最多发送 5 个提案
- 提案 48 小时后自动过期（惰性检查）
- 屏蔽用户时自动作废双方之间的待处理提案
- 需拥有活跃的匹配偏好才可发送

### 2.4 模式四：直接邀请（Booking Invite）

用户可通过直接邀请某位球友约球，**跳过 NTRP 水平范围校验**。

**设计理由：** 朋友或熟人之间互相了解彼此水平，不需要系统强制限制水平差距。

**流程：**

1. 在对方个人主页或聊天中点击"邀请约球"
2. 填写约球信息（`POST /api/v1/bookings/invites`）：球场、类型、日期时间、性别要求、费用、备注，**无需填写水平范围要求**
3. 对方收到 `BOOKING_INVITE_RECEIVED` 通知
4. 对方接受（`POST /api/v1/bookings/invites/{id}/accept`）→ **自动创建已确认的约球 + 聊天会话**，邀请记录关联 `booking_id`
5. 对方拒绝（`POST /api/v1/bookings/invites/{id}/reject`）→ 通知发起人

**查看邀请：**

- `GET /api/v1/bookings/invites/sent` — 我发出的邀请
- `GET /api/v1/bookings/invites/received` — 我收到的邀请
- `GET /api/v1/bookings/invites/{id}` — 邀请详情（仅邀请双方可查看）

**规则：**

- 被拉黑的用户不可发起邀请
- 信誉积分 ≥ 60 才可发起
- 不可向同一用户发送重复的待处理邀请
- 约球成立后的信誉积分规则与其他模式一致（取消扣分等）
- 双打场景：发起人可邀请指定球友组队，同样跳过水平校验

**数据模型：** `BookingInvite` — id, inviter_id, invitee_id, court_id, match_type, play_date, start_time, end_time, gender_requirement, cost_per_person, description, status (PENDING/ACCEPTED/REJECTED/EXPIRED), booking_id (接受后关联)

---

## 3. 信誉积分体系

| 项目                    | 分值                   |
| ----------------------- | ---------------------- |
| 初始分数                | 80 分                  |
| 满分上限                | 100 分                 |
| 分数下限                | 0 分                   |
| 按时赴约                | +5 分/次               |
| 首次违规取消            | 不扣分，发出警告提醒   |
| 第2次起：24h 前取消     | -1 分                  |
| 第2次起：12-24h 前取消  | -2 分                  |
| 第2次起：2h 内取消/爽约 | -5 分                  |
| 天气原因取消            | 不扣分（系统自动检测） |

**积分范围：** 0-100 分，所有变动通过 `apply_credit_change()` 统一处理，自动 clamp 到有效范围。

**首次违规警告：** 用户首次取消约球（`cancel_count == 0` 时），积分不扣除，仅发出 `FIRST_CANCEL_WARNING` 警告。

**限制：** 信誉积分低于 60 分 → 限制发起约球和直接邀请。

**积分变动记录：** 所有积分变动记入 `CreditLog` 表，包含 user_id、delta、reason（枚举值）、description、created_at。

**积分变动类型（`CreditReason`枚举）：** ATTENDED, FIRST_CANCEL_WARNING, CANCEL_24H, CANCEL_12_24H, CANCEL_2H, NO_SHOW, WEATHER_CANCEL, ADMIN_ADJUST

---

## 4. 天气集成

`GET /api/v1/weather` — 查询指定球场和日期的天气信息。

**请求参数：** court_id, date, start_time

**数据来源：** 和风天气 API（QWeather，支持国内 + 香港）

- 7 天逐日预报 + 24 小时逐时预报
- Redis 缓存，TTL 根据预报时间距离动态调整（30 分钟 / 1 小时 / 3 小时）

**天气信息展示：**

- 约球详情页显示该时段天气（温度、降雨概率、风力、紫外线指数）
- 约球列表中天气图标快速预览

**恶劣天气预警与免责取消（`allows_free_cancel`）：**

| 预警条件               | 触发         |
| ---------------------- | ------------ |
| 降雨概率 ≥ 80%         | 免责取消     |
| 台风预警               | 免责取消     |
| 暴雨预警               | 免责取消     |
| 气温 ≥ 38°C            | 免责取消     |
| 高温（35°C+）          | 提示中暑风险 |
| 强紫外线（UV 指数 8+） | 提示防晒     |

**约球取消联动：** `cancel_booking()` 会自动查询天气，若 `allows_free_cancel=True`，则取消不扣信誉积分（`WEATHER_CANCEL`）。

---

## 5. 社交功能

### 5.1 关注与好友

- 单向关注（类似微博），无需对方同意
- 互相关注 = 好友（在查询时动态检测 `is_mutual`）
- 关注时触发 `NEW_FOLLOWER` 通知；互关时额外触发 `NEW_MUTUAL` 通知
- 好友约球时收到优先通知
- 屏蔽用户时自动删除关注关系

### 5.2 评价系统（双盲评价）

- 打完球后双方互评（**24 小时内**）
- 评分维度：球技水平（skill）、守时程度（punctuality）、球品态度（sportsmanship）（各 1-5 星）
- 可选文字评价
- **双盲机制：** 评价提交后不立即公开展示，只有当双方都提交评价后才同时揭示（`REVIEW_REVEALED` 通知），避免先评价者影响对方
- 评价公开展示在个人主页（显示已揭示的评价 + 三维平均分）
- `is_hidden` 标志位：被管理员隐藏的评价不展示
- 恶意评价可举报，管理员审核
- `GET /api/v1/reviews/pending` — 查看待评价列表

### 5.3 打球记录与统计

- 自动记录每次约球（日期、球场、对手）
- `GET /api/v1/users/{user_id}/stats` — 统计：总场次、本月场次、单打/双打分别计数、常去球场 Top3、最常搭档
- `GET /api/v1/users/{user_id}/calendar` — 月度日历视图：返回指定年月的比赛日期列表

---

## 6. 聊天系统

### 6.1 聊天类型

- **私聊（PRIVATE）：** 约球确认后自动创建聊天会话
- **群聊（GROUP）：** 双打约球自动建群（2-4人）、赛事参赛者群聊
- **约球聊天：** `ChatRoom.booking_id` 关联约球
- **赛事聊天：** `ChatRoom.event_id` 关联赛事（赛事开始时自动创建）

### 6.2 消息类型（`MessageType`）

- `TEXT` — 文字消息（经敏感词过滤）
- `IMAGE` — 图片
- `LOCATION` — 位置分享
- `BOOKING_CARD` — 约球卡片

### 6.3 实时通信

- **WebSocket：** `WS /api/v1/chat/ws?token=<jwt>` — 实时双向通信
  - 认证方式：查询参数中传递 JWT token
  - 心跳保活：ping/pong 机制
  - 发送消息广播到房间内所有在线参与者
  - `ConnectionManager` 管理 WebSocket 连接
- **HTTP REST：** 同时支持 HTTP 接口发送消息（适用于离线恢复等场景）

### 6.4 聊天功能

- `GET /api/v1/chat/rooms` — 聊天室列表（过滤已屏蔽用户的私聊；包含最后一条消息 + 未读数）
- `GET /api/v1/chat/rooms/{room_id}/messages` — 消息列表（游标分页，`before_id` 参数）
- `POST /api/v1/chat/rooms/{room_id}/messages` — 发送消息
- `POST /api/v1/chat/rooms/{room_id}/read` — 标记已读（更新 `last_read_at`）
- 未读消息计算基于 `ChatParticipant.last_read_at`

### 6.5 内容安全

- **敏感词过滤：** `blocked_words.txt` 自定义词库，对 TEXT 类型消息做大小写不敏感的子串匹配
- 聊天中可举报不当内容
- 管理员可删除单条消息（`DELETE /api/v1/admin/chat/messages/{message_id}`）

### 6.6 只读模式

- `ChatRoom.is_readonly` 标志位
- 约球取消或赛事取消时，关联的聊天室自动设为只读
- HTTP 和 WebSocket 发送路径均会检查只读状态

### 6.7 参与者同步

- 约球参与者状态变更（接受/拒绝/取消）时，自动同步聊天室成员

---

## 7. 社区赛事

### 7.1 赛事类型

- 单打淘汰赛（`SINGLES_ELIMINATION`）
- 双打淘汰赛（`DOUBLES_ELIMINATION`）
- 循环赛（`ROUND_ROBIN`）— 小组赛

### 7.2 发起赛事

- 任何用户可发起（需信誉积分 ≥ 80）
- 赛事初始状态为 `DRAFT`
- 设置：赛事名称、类型、水平范围（min_ntrp/max_ntrp）、性别要求、人数上限
- 设置：日期范围（start_date/end_date）、报名截止日（registration_deadline）、球场
- 设置：赛制规则 — 每盘局数（games_per_set，默认 6）、盘数（num_sets，默认 3）、是否抢七（match_tiebreak）
- 设置：报名费（可选，预留接口）

### 7.3 赛事生命周期

```
DRAFT → OPEN（发布） → IN_PROGRESS（开始） → COMPLETED / CANCELLED
```

1. **发布（publish）：** DRAFT → OPEN，开放报名
2. **报名（join）：** 校验 NTRP、性别、屏蔽、容量
3. **开始（start）：** 自动生成赛程
   - **种子排位：** 根据 NTRP 等级 + 信誉积分综合排序
   - **淘汰赛：** 自动生成对阵树（draw），种子选手分散在不同半区
   - **循环赛：** 按组生成对阵（group_name 分组）
   - **自动创建赛事群聊**
4. **比分录入与确认：**
   - 参赛者提交比分（`POST /api/v1/events/matches/{match_id}/score`）— 含各盘比分和抢七分
   - 对手确认比分（`POST /api/v1/events/matches/{match_id}/confirm`）— 双方确认制
   - 对手争议比分（`POST /api/v1/events/matches/{match_id}/dispute`）— 退回重新提交
   - 弃权（`POST /api/v1/events/matches/{match_id}/walkover`）— 自动判负
   - 组织者覆盖比分（`PATCH /api/v1/events/matches/{match_id}/score`）— 争议时由组织者裁定
5. **赛事结束：** 所有比赛完成后标记为 COMPLETED

### 7.4 赛事页面展示

- `GET /api/v1/events/{event_id}/bracket` — 赛程对阵图（淘汰赛树状图）
- `GET /api/v1/events/{event_id}/standings` — 积分榜（循环赛）
- `GET /api/v1/events/{event_id}/matches` — 比赛列表（可按轮次、小组筛选）
- 参赛者列表 + 水平 + 种子排位
- 赛事群聊入口

### 7.5 赛事通知

- `EVENT_REGISTRATION_OPEN` — 报名开始
- `EVENT_JOINED` — 成功报名
- `EVENT_STARTED` — 赛事开始
- `EVENT_MATCH_READY` — 比赛就绪
- `EVENT_SCORE_SUBMITTED` — 对手提交了比分
- `EVENT_SCORE_CONFIRMED` — 比分确认
- `EVENT_SCORE_DISPUTED` — 比分被争议
- `EVENT_WALKOVER` — 对手弃权
- `EVENT_ELIMINATED` — 被淘汰
- `EVENT_COMPLETED` — 赛事结束
- `EVENT_CANCELLED` — 赛事取消

---

## 8. 推送通知

### 8.1 通知系统架构

**应用内通知：** 所有 46 种通知类型均支持应用内轮询（`GET /api/v1/notifications`）。

**远程推送（FCM）：** 部分高优先级通知通过 Firebase Cloud Messaging 推送到设备。

**推送架构：**

```
事件发生 → create_notification() → 写入数据库 + 入 Redis 队列
                                     ↓
                              后台推送 Worker（push_worker）
                                     ↓
                              Firebase Admin SDK → FCM → 设备
```

**智能推送：** 如果用户当前有活跃的 WebSocket 连接（在线聊天中），则跳过远程推送（避免重复打扰）。

**设备 Token 管理：**

- `POST /api/v1/devices` — 注册 FCM 设备 token（支持 iOS / Android 平台）
- `DELETE /api/v1/devices/{token}` — 移除设备 token
- 推送失败时自动清理失效的 token

### 8.2 通知类型汇总（46 种）

| 分类     | 通知类型                                                                                                                                                                                                        |
| -------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 约球     | BOOKING_JOINED, BOOKING_ACCEPTED, BOOKING_REJECTED, BOOKING_CANCELLED, BOOKING_CONFIRMED, BOOKING_COMPLETED                                                                                                     |
| 直接邀请 | BOOKING_INVITE_RECEIVED, BOOKING_INVITE_ACCEPTED, BOOKING_INVITE_REJECTED                                                                                                                                       |
| 匹配     | MATCH_PROPOSAL_RECEIVED, MATCH_PROPOSAL_ACCEPTED, MATCH_PROPOSAL_REJECTED, MATCH_SUGGESTION                                                                                                                     |
| 社交     | NEW_FOLLOWER, NEW_MUTUAL                                                                                                                                                                                        |
| 评价     | REVIEW_REVEALED                                                                                                                                                                                                 |
| 理想球友 | IDEAL_PLAYER_GAINED, IDEAL_PLAYER_LOST                                                                                                                                                                          |
| 聊天     | NEW_CHAT_MESSAGE                                                                                                                                                                                                |
| 赛事     | EVENT_REGISTRATION_OPEN, EVENT_JOINED, EVENT_STARTED, EVENT_MATCH_READY, EVENT_SCORE_SUBMITTED, EVENT_SCORE_CONFIRMED, EVENT_SCORE_DISPUTED, EVENT_WALKOVER, EVENT_ELIMINATED, EVENT_COMPLETED, EVENT_CANCELLED |
| 管理     | REPORT_RESOLVED, ACCOUNT_WARNED, ACCOUNT_SUSPENDED                                                                                                                                                              |

**可推送类型（FCM）：** 仅部分高优先级类型走远程推送，其余仅应用内通知。

### 8.3 用户设置

- 按类型开关通知
- 免打扰时段
- 通知语言跟随用户语言偏好

---

## 9. 支付与费用

**MVP 阶段：** 仅做费用展示（AA 金额参考），不走平台支付。球员线下自行 AA。

**预留接口：** 后续可接入 Apple Pay、微信支付、支付宝，支持球场费 AA 分摊和赛事报名费收取。

---

## 10. 安全与合规

### 10.1 举报系统

- 举报类型（`ReportReason`）：爽约（NO_SHOW）、骚扰（HARASSMENT）、虚假信息（FALSE_INFO）、不当言论（INAPPROPRIATE）、其他（OTHER）
- **举报目标多态化（`ReportTargetType`）：** 可举报用户（USER）或评价（REVIEW）
- 举报后 24h 内人工审核
- 处罚阶梯（`ReportResolution`）：
  - `DISMISSED` — 驳回
  - `WARNED` — 警告（发送 `ACCOUNT_WARNED` 通知）
  - `CONTENT_HIDDEN` — 隐藏内容（用于评价举报，设置 `review.is_hidden = True`）
  - `SUSPENDED` — 封号（设置 `user.is_suspended = True`，发送 `ACCOUNT_SUSPENDED` 通知）

### 10.2 拉黑机制

- 拉黑后双方不可见、不匹配、不能私信
- 拉黑时自动作废双方之间的待处理匹配提案
- 拉黑时自动删除关注关系
- `is_blocked(session, a, b)` 对称检查——任一方屏蔽都生效
- 解除拉黑为硬删除（非软删除）
- 可在设置中管理黑名单

### 10.3 敏感词过滤

- `app/data/blocked_words.txt` 自定义敏感词库
- 对聊天 TEXT 类型消息做大小写不敏感的子串匹配
- 匹配到敏感词则拒绝发送

### 10.4 实名认证（可选）

- 头像真人审核（AI 识别 + 人工复审）
- 已认证用户显示认证标识（`is_verified`），匹配优先级更高

### 10.5 法律合规

- 用户服务协议
- 隐私政策（符合《个人信息保护法》+ 香港 PDPO）
- 运动风险免责声明（首次约球前需确认）
- App Store 审核要求：举报功能、内容审核

---

## 11. 多语言 (i18n)

- 🇨🇳 简体中文 (zh-Hans)
- 🇭🇰 繁體中文 (zh-Hant) — 香港默认
- 🇬🇧 English (en)

**实现方式：**

- iOS 端：SwiftUI 原生 Localizable.strings
- 后端：
  - `app/i18n.py` — `t(key, lang)` 函数，所有用户可见的错误消息和推送文案均支持三语
  - 通过 `Accept-Language` 请求头确定语言（`Lang` 依赖注入）
  - 默认语言：zh-Hant
- 用户生成内容（约球帖、评价等）：原文展示，不翻译
- 首次启动跟随系统语言，设置页可手动切换

---

## 12. 管理后台

### 12.1 权限体系

**两级管理员：**

- `ADMIN` — 普通管理员，可执行大部分管理操作
- `SUPERADMIN` — 超级管理员，拥有所有权限（解封用户、修改角色、删除球场）

**用户角色（`UserRole`枚举）：** USER、ADMIN、SUPERADMIN

**权限控制：** 通过 `AdminUser` 和 `SuperAdminUser` 依赖注入实现路由级权限校验。

### 12.2 管理仪表盘

`GET /api/v1/admin/dashboard/stats` — 返回平台概览数据：

- `total_users` — 总用户数
- `suspended_users` — 被封用户数
- `pending_reports` — 待处理举报数
- `pending_courts` — 待审核球场数
- `active_bookings` — 进行中约球数
- `active_events` — 进行中赛事数

### 12.3 用户管理

| 端点                                         | 权限       | 说明                                                   |
| -------------------------------------------- | ---------- | ------------------------------------------------------ |
| `GET /api/v1/admin/users`                    | Admin      | 用户列表（筛选：角色、城市、封禁状态）                 |
| `GET /api/v1/admin/users/{id}`               | Admin      | 用户详情（含约球数、平均评分）                         |
| `PATCH /api/v1/admin/users/{id}/suspend`     | Admin      | 封禁用户                                               |
| `PATCH /api/v1/admin/users/{id}/unsuspend`   | SuperAdmin | 解封用户                                               |
| `PATCH /api/v1/admin/users/{id}/role`        | SuperAdmin | 修改用户角色                                           |
| `POST /api/v1/admin/users/{id}/reset-credit` | Admin      | 重置信誉积分至 80、cancel_count 归零、重新评估理想球友 |

### 12.4 球场管理

| 端点                                      | 权限       | 说明                             |
| ----------------------------------------- | ---------- | -------------------------------- |
| `GET /api/v1/admin/courts`                | Admin      | 球场列表（筛选：审核状态、城市） |
| `PATCH /api/v1/admin/courts/{id}/approve` | Admin      | 审核通过球场                     |
| `PATCH /api/v1/admin/courts/{id}/reject`  | Admin      | 拒绝（删除）未审核球场           |
| `DELETE /api/v1/admin/courts/{id}`        | SuperAdmin | 删除任意球场                     |

### 12.5 举报管理

| 端点                                       | 权限  | 说明                                |
| ------------------------------------------ | ----- | ----------------------------------- |
| `GET /api/v1/admin/reports`                | Admin | 举报列表（筛选：状态）              |
| `GET /api/v1/admin/reports/{id}`           | Admin | 举报详情                            |
| `PATCH /api/v1/admin/reports/{id}/resolve` | Admin | 处理举报（驳回/警告/隐藏内容/封号） |

### 12.6 约球管理

| 端点                                       | 权限  | 说明                                       |
| ------------------------------------------ | ----- | ------------------------------------------ |
| `GET /api/v1/admin/bookings`               | Admin | 约球列表（筛选：状态）                     |
| `PATCH /api/v1/admin/bookings/{id}/cancel` | Admin | 强制取消约球（通知参与者、聊天室设为只读） |

### 12.7 赛事管理

| 端点                                                      | 权限  | 说明                   |
| --------------------------------------------------------- | ----- | ---------------------- |
| `GET /api/v1/admin/events`                                | Admin | 赛事列表（筛选：状态） |
| `PATCH /api/v1/admin/events/{id}/cancel`                  | Admin | 强制取消赛事           |
| `DELETE /api/v1/admin/events/{id}/participants/{user_id}` | Admin | 移除参赛者             |

### 12.8 聊天管理

| 端点                                              | 权限  | 说明             |
| ------------------------------------------------- | ----- | ---------------- |
| `DELETE /api/v1/admin/chat/messages/{message_id}` | Admin | 删除单条聊天消息 |

### 12.9 审计日志

`GET /api/v1/admin/audit` — 所有管理操作均记入审计日志（`AdminAuditLog` 表），包含：

- `admin_id` — 操作管理员
- `action` — 操作类型（`AdminAction` 枚举：12 种操作）
- `target_type` + `target_id` — 操作目标
- `detail` — 操作详情（JSON）
- `created_at` — 操作时间

**操作类型（`AdminAction`枚举）：** USER_SUSPENDED, USER_UNSUSPENDED, USER_ROLE_CHANGED, USER_CREDIT_RESET, COURT_APPROVED, COURT_REJECTED, COURT_DELETED, REPORT_RESOLVED, BOOKING_CANCELLED, EVENT_CANCELLED, EVENT_PARTICIPANT_REMOVED, MESSAGE_DELETED

---

## 13. 约球助理 Agent

### 13.1 概述

App 内集成 AI 约球助理，用户输入一段自然语言（例如："这周末下午在维园想打单打，3.5 左右，AA"），后端调用 LLM 解析意图并返回结构化字段，iOS 端预填发布表单，用户确认后提交。

### 13.2 架构

```
iOS 输入自然语言 → POST /api/v1/assistant/parse-booking
                    → LLM Adapter (Claude / OpenAI)
                    → 结构化结果 + 球场模糊匹配
                    ← 返回预填字段 JSON
iOS 展示预填表单 → 用户确认/修改 → 正常走 create_booking 流程
```

**处理模式：后端解析。** API key 不暴露在客户端，后端可直接查询数据库做球场模糊匹配和用户偏好补全，方便 prompt 版本管理和 A/B 测试。

### 13.3 LLM Adapter

当前实现为 Claude provider（使用 tool use / structured output）：

- `LLM_PROVIDER`：默认 `claude`，可选 `openai`
- `ANTHROPIC_API_KEY`：Claude API 密钥
- `ANTHROPIC_MODEL`：默认 `claude-sonnet-4-20250514`
- `OPENAI_API_KEY`：OpenAI API 密钥（预留）

统一接口：`LLMProvider` 协议，`parse(prompt, schema) -> dict`。新增 provider 只需实现该协议。

### 13.4 解析策略

使用 structured output / tool use 让 LLM 返回固定 JSON schema：

```json
{
  "match_type": "singles | doubles | null",
  "play_date": "YYYY-MM-DD | null",
  "start_time": "HH:MM | null",
  "end_time": "HH:MM | null",
  "court_keyword": "用户提及的球场关键词 | null",
  "min_ntrp": "3.0 | null",
  "max_ntrp": "4.0 | null",
  "gender_requirement": "male_only | female_only | any | null",
  "cost_description": "AA | 免费 | null"
}
```

- 未识别的字段返回 `null`，前端对应留空让用户手动填
- `court_keyword` 由后端在 Court 表中做名称模糊匹配，返回匹配到的 court_id 和球场名，未匹配到则返回 null
- System prompt 会注入当前日期和城市上下文

### 13.5 后端模块

- `app/services/llm.py` — LLM adapter 层，Claude provider 实现
- `app/services/assistant.py` — 约球助理核心逻辑：构建 prompt、调用 LLM、解析响应、球场模糊匹配
- `app/routers/assistant.py` — `POST /api/v1/assistant/parse-booking`
- `app/schemas/assistant.py` — 请求体（自然语言文本）和响应体（解析出的结构化字段）

### 13.6 成本控制

- 配置项 `ASSISTANT_RATE_LIMIT`：每用户每小时调用次数上限（默认 10 次）
- 使用 Redis 做限流计数（`incr` + TTL）
- 日志记录每次调用的 token 用量和耗时

### 13.7 对现有代码的影响

- `app/config.py` — 新增 LLM 相关配置项（provider、API keys、model、rate limit）
- `app/main.py` — 注册 assistant router
- **不修改现有 booking 流程**，助理只负责"解析"，最终提交仍走 `create_booking`

---

## 14. SwiftData 离线缓存（iOS 技术架构补充）

### 14.1 概述

开发环境为 macOS Tahoe，利用最新 SwiftData 特性进行本地缓存，提升在网球场（信号可能不好）时的使用体验。

### 14.2 缓存策略分层

| 数据类型             | 缓存策略                         | 理由                             |
| -------------------- | -------------------------------- | -------------------------------- |
| 我的约球列表         | SwiftData 持久化，每次拉取时更新 | 到球场后需要看约球详情、对手信息 |
| 约球详情（含参与者） | SwiftData 持久化                 | 同上，核心离线场景               |
| 球场信息             | SwiftData 持久化，长效缓存       | 球场数据变动少                   |
| 聊天消息             | SwiftData 持久化，增量同步       | 离线时可查看历史消息             |
| 通知列表             | 内存缓存，不持久化               | 非关键离线数据                   |
| 约球列表（广场）     | 内存缓存 + 短 TTL                | 实时性要求高，缓存价值低         |

### 14.3 同步机制

- **Server wins：** 网络恢复时自动拉取最新数据，以服务端为准
- **离线写队列：** 离线期间的写操作（如发消息）排队，网络恢复后按序提交
- **单一数据源：** SwiftData 的 `ModelContainer` 作为单一数据源，ViewModel 从 SwiftData 读取而非直接持有网络响应

### 14.4 对后端的影响

**无。** 现有 API 的分页和筛选接口已足够支持增量拉取，不需要后端改动。

---

## 15. 理想球友机制

### 15.1 概述

对"高赴约率、高评价、从未违规"的用户标记为"理想球友"，在智能匹配和约球列表中给予更高曝光权重，形成正向社交循环。

### 15.2 达标条件

**以下四个条件全部满足时，标记为理想球友：**

| 条件             | 判定方式                                                            |
| ---------------- | ------------------------------------------------------------------- |
| 信誉积分 ≥ 90    | `user.credit_score >= 90`                                           |
| 从未违规取消     | `user.cancel_count == 0`                                            |
| 完成约球 ≥ 10 场 | 统计 BookingParticipant（status=accepted）关联的已完成 Booking 数量 |
| 平均评价 ≥ 4.0   | 收到的 Review 三维评分（skill, punctuality, sportsmanship）均分     |

### 15.3 数据模型变更

- `User` 表新增 `is_ideal_player: bool`，默认 `False`
- 不新增单独的表，直接在 User 上标记
- 需要一条 Alembic migration

### 15.4 评估触发时机（事件驱动）

| 触发事件     | 触发点                                       | 原因                             |
| ------------ | -------------------------------------------- | -------------------------------- |
| 约球完成     | `services/booking.py → complete_booking()`   | 场次 +1，信誉积分变动            |
| 收到新评价   | `services/review.py → create_review()`       | 均分可能变化                     |
| 信誉积分变动 | `services/credit.py → apply_credit_change()` | 可能跌破 90 或 cancel_count 变化 |

### 15.5 新增模块

- `app/services/ideal_player.py` — `evaluate_ideal_status(session, user_id) -> bool`，查询四个条件，更新 `user.is_ideal_player`

### 15.6 匹配与展示

- **约球列表排序：** 理想球友发布的约球帖优先展示
- **用户搜索排序：** 理想球友优先排列
- **智能匹配加权：** 理想球友在匹配权重中获得 5% 额外加成
- **个人主页：** 展示"理想球友"徽章（前端根据 `is_ideal_player` 字段渲染）

### 15.7 降级规则

任一条件不满足时自动移除标记。例如：用户取消一次约球后 `cancel_count` 变为 1，下次评估时 `is_ideal_player` 设为 `False`。

### 15.8 通知

状态变更时通知用户，新增两个 `NotificationType` 枚举值：

- `IDEAL_PLAYER_GAINED` — 用户首次达标或恢复达标时推送，如："恭喜你成为理想球友！"
- `IDEAL_PLAYER_LOST` — 用户失去标记时推送，如："你的理想球友资格已移除"

在 `evaluate_ideal_status()` 中，对比评估前后的 `is_ideal_player` 值，仅在状态**发生变化**时创建通知（避免重复推送）。

### 15.9 对现有代码的影响

- `models/user.py` — 新增 `is_ideal_player` 字段
- `models/notification.py` — `NotificationType` 枚举新增 `IDEAL_PLAYER_GAINED`、`IDEAL_PLAYER_LOST`
- `services/credit.py` — `apply_credit_change()` 末尾调用评估
- `services/review.py` — `create_review()` 末尾调用评估
- `services/booking.py` — `complete_booking()` 末尾调用评估
- `routers/bookings.py` / `schemas/` — 响应中暴露 `is_ideal_player`
- Alembic migration 新增字段 + 枚举值

---

## 16. 技术架构

### 16.1 系统架构

```
iOS App (SwiftUI + SwiftData) ←→ FastAPI Backend (Python) ←→ PostgreSQL + Redis
                                                               ↕
                                                         第三方服务
                                                         • Google Maps
                                                         • 和风天气 (QWeather)
                                                         • Firebase Cloud Messaging (FCM)
                                                         • 微信开放平台（预留）
                                                         • Google OAuth（预留）
                                                         • SMS 短信服务（MVP: 固定验证码）
                                                         • Claude API (Anthropic)
                                                         • OpenAI API（预留）
```

### 16.2 后端模块

| 模块                    | 关键文件                                | 说明                                                        |
| ----------------------- | --------------------------------------- | ----------------------------------------------------------- |
| Auth（认证）            | `auth.py`                               | JWT（access + refresh）、bcrypt、多 provider                |
| User（用户）            | `user.py`, `user_search.py`, `stats.py` | 资料管理、搜索、统计、日历                                  |
| Booking（约球）         | `booking.py`, `booking_invite.py`       | 发布、报名、确认、取消、完成、直接邀请                      |
| Matching（匹配）        | `matching.py`, `match_proposal.py`      | 偏好设置、评分匹配、被动匹配、提案、推荐约球帖              |
| Chat（聊天）            | `chat.py`                               | WebSocket + REST、聊天室自动创建、敏感词过滤、只读模式      |
| Event（赛事）           | `event.py`                              | 创建、报名、种子排位、赛程生成、比分双确认、对阵图、积分榜  |
| Credit（信用）          | `credit.py`                             | 积分计算（0-100 clamp）、首次警告、记录                     |
| Review（评价）          | `review.py`                             | 双盲互评、24h 窗口、揭示通知                                |
| Report（举报）          | `report.py`                             | 多态目标（用户/评价）、管理员处理                           |
| Block（屏蔽）           | `block.py`                              | 对称屏蔽、联动（提案作废、关注删除）                        |
| Follow（关注）          | `follow.py`                             | 单向关注、互关检测、关注/互关通知                           |
| Notification（通知）    | `notification.py`                       | 应用内轮询、46 种类型、入 Redis 推送队列                    |
| Push（推送）            | `push.py`                               | 后台 Worker、FCM multicast、失效 token 清理、WebSocket 感知 |
| Device（设备）          | `device.py`                             | FCM 设备 token 注册/移除                                    |
| Weather（天气）         | `weather.py`                            | QWeather API、Redis 动态 TTL 缓存、恶劣天气免责取消         |
| IdealPlayer（理想球友） | `ideal_player.py`                       | 事件驱动评估、标记管理                                      |
| Assistant（约球助理）   | `llm.py`, `assistant.py`                | 自然语言解析、Claude provider、Redis 限流、球场模糊匹配     |
| NTRP Guide（水平指南）  | `ntrp_guide.py`                         | 1.5-7.0 等级三语描述                                        |
| Word Filter（敏感词）   | `word_filter.py`                        | 自定义词库子串匹配                                          |
| Admin（管理后台）       | `admin.py`                              | 用户/球场/举报/约球/赛事/聊天管理、仪表盘、审计日志         |

### 16.3 核心数据模型

- **User** — id, 昵称, 头像, 性别, 城市, NTRP等级, ntrp_label, 信誉积分, cancel_count, bio, years_playing, 语言偏好, 角色(USER/ADMIN/SUPERADMIN), is_verified, is_active, is_suspended, is_ideal_player
- **UserAuth** — id, user_id, provider(PHONE/WECHAT/GOOGLE/USERNAME/APPLE), provider_user_id, password_hash, email, email_verified
- **Booking** — id, 发起人, 类型(单打/双打), 球场, 时间, 水平范围, 性别要求, max_participants(自动计算), 费用, 状态(open/confirmed/completed/cancelled)
- **BookingParticipant** — booking_id, user_id, 状态(pending/accepted/rejected/cancelled)
- **BookingInvite** — id, inviter_id, invitee_id, 球场, 类型, 时间, 性别要求, 费用, 备注, 状态(pending/accepted/rejected/expired), booking_id
- **Court** — id, 名称, 地址, 经纬度, 城市, 类型(indoor/outdoor), **surface_type(hard/clay/grass)**, created_by, is_approved
- **MatchPreference** — user_id(唯一), 匹配类型, NTRP范围, 性别偏好, 最大距离, is_active
- **MatchTimeSlot** — preference_id, 星期几(0-6), 开始/结束时间
- **MatchPreferenceCourt** — preference_id, court_id
- **MatchProposal** — id, proposer_id, target_id, court_id, 类型, 日期时间, 留言, 状态(pending/accepted/rejected/expired)
- **ChatRoom** — id, 类型(private/group), booking_id, **event_id**, 名称, **is_readonly**
- **ChatParticipant** — room_id, user_id, joined_at, **last_read_at**
- **Message** — id, room_id, sender_id, 类型(text/image/location/booking_card), 内容, is_deleted
- **Event** — id, 创建人, 名称, 类型(singles_elimination/doubles_elimination/round_robin), 赛制(盘数/局数/抢七), 水平范围, 性别, 人数上限, 日期范围, 报名截止, 报名费, 状态(draft/open/in_progress/completed/cancelled)
- **EventParticipant** — event_id, user_id, seed, group_name, team_name, 状态(registered/confirmed/withdrawn/eliminated)
- **EventMatch** — event_id, round, match_order, player_a/b, winner_id, group_name, 状态(pending/submitted/confirmed/disputed/walkover), submitted_by
- **EventSet** — match_id, set_number, score_a, score_b, tiebreak_a, tiebreak_b
- **Review** — 评价人, 被评价人, booking_id, skill/punctuality/sportsmanship评分, 文字, is_hidden
- **Follow** — follower_id, followed_id
- **Report** — 举报人, 被举报人, target_type, target_id, 原因, 状态, 处理结果, resolved_by
- **Block** — blocker_id, blocked_id
- **CreditLog** — user_id, delta, reason(枚举), description
- **Notification** — recipient_id, actor_id, type(46种), target_type, target_id, is_read
- **DeviceToken** — user_id, platform(ios/android), token(4096)
- **AdminAuditLog** — admin_id, action(12种枚举), target_type, target_id, detail(JSON)

### 16.4 iOS 技术选型

- UI 框架：SwiftUI（iOS 16+）
- 架构模式：MVVM
- 网络层：URLSession + async/await
- WebSocket：URLSessionWebSocketTask
- 本地存储：SwiftData（离线缓存 + 数据持久化）+ Keychain（凭证）
- 地图：MapKit + Google Maps SDK
- 推送：Firebase Cloud Messaging (FCM) + UserNotifications
- 图片处理：Kingfisher（缓存 + 加载）

### 16.5 扩展性

| 用户规模 | 配置                              |
| -------- | --------------------------------- |
| 1-1万    | 单台 2核4G                        |
| 1-10万   | 4核8G + Redis                     |
| 10-50万  | 2台应用 + DB读写分离 + Redis集群  |
| 50-100万 | 聊天服务独立拆分 + 负载均衡 + CDN |

---

## 17. MVP 范围

**首期上线城市：** 香港

**包含功能：** 以上所有功能（支付仅做展示，预留接口）

**已实现功能：**

- 完整的用户系统（注册/登录/资料/搜索/统计）
- 约球四种模式（发布/智能匹配/匹配提案/直接邀请）
- 信誉积分体系（含首次警告机制）
- 天气集成（QWeather + 免责取消联动）
- 社交功能（关注/双盲评价/统计日历）
- 实时聊天系统（WebSocket + REST + 敏感词过滤）
- 社区赛事（淘汰赛/循环赛 + 种子排位 + 比分双确认）
- 推送通知（FCM + 后台 Worker + 智能推送）
- 管理后台（用户/球场/举报/约球/赛事/聊天管理 + 审计日志）
- 约球助理 Agent（自然语言解析，Claude provider）
- SwiftData 离线缓存（iOS 端，提升弱信号体验）
- 理想球友机制（高信誉用户标记与优先曝光）
- NTRP 等级指南（三语详细描述）
- 用户搜索（球场附近 + 多维筛选）

**尚未实现（已预留）：**

- Sign in with Apple（待实现）
- 微信一键登录（schema 和枚举已定义，路由未实现）
- Google 账号登录（schema 和枚举已定义，路由未实现）
- 信誉积分历史查询（服务层已实现，路由未暴露）
- 管理员积分调整（`ADMIN_ADJUST` 枚举已定义，入口未实现）
- 阶梯赛（Ladder）赛制

**后续扩展：**

- 开放更多城市（北京、上海、杭州、广州、深圳、武汉、成都、天津、沈阳等等）
- 接入支付功能
- 实现微信 / Google 登录
- 根据用户反馈迭代
