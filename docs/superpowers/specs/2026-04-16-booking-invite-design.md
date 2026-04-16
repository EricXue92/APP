# 私信约球（直接邀请）设计文档

## 概述

用户可以直接邀请指定球友约球，跳过 NTRP 水平范围校验。朋友或熟人之间互相了解彼此水平，不需要系统限制水平差距。

邀请需要对方确认后才会创建 Booking，对方有完全的选择权。

## 核心流程

1. A 在 B 的个人主页点击"邀请约球"
2. A 填写约球信息（时间、球场、类型等），**无需填写水平范围**
3. B 收到邀请通知（`BOOKING_INVITE_RECEIVED`）
4. B 查看邀请详情，选择接受或拒绝
5. **接受：** 自动创建 Booking（双方均为 accepted）→ Booking 直接 confirmed → 创建 ChatRoom → 通知 A
6. **拒绝：** 通知 A，流程结束
7. **过期：** `play_date` 已过且仍为 pending → 视为过期

## 数据模型

### BookingInvite（新表）

```
booking_invites
├── id: UUID (PK)
├── inviter_id: UUID → FK users.id
├── invitee_id: UUID → FK users.id
├── court_id: UUID → FK courts.id
├── match_type: MatchType (singles/doubles)
├── play_date: date
├── start_time: time
├── end_time: time
├── gender_requirement: GenderRequirement (默认 any)
├── cost_per_person: int | None
├── description: str | None
├── status: InviteStatus (pending/accepted/rejected/expired)
├── booking_id: UUID | None → FK bookings.id (accepted 后填充)
├── created_at: datetime
└── updated_at: datetime
```

关键设计：模型层面没有 `min_ntrp` / `max_ntrp` 字段，从根本上跳过水平校验。`booking_id` 仅在 accepted 后指向自动创建的 Booking。

### 枚举

```python
class InviteStatus(str, enum.Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
```

## API 设计

所有接口挂在 `/api/v1/bookings/invites` 下。

### POST /api/v1/bookings/invites — 发起邀请

**请求体：**

```json
{
  "invitee_id": "uuid",
  "court_id": "uuid",
  "match_type": "singles",
  "play_date": "2026-04-20",
  "start_time": "14:00",
  "end_time": "16:00",
  "gender_requirement": "any",
  "cost_per_person": null,
  "description": "一起打球吧"
}
```

**校验规则：**

| 条件                      | 响应 |
| ------------------------- | ---- |
| 信用分 < 60               | 403  |
| 球场不存在或未审核        | 404  |
| play_date < today         | 400  |
| 邀请自己                  | 400  |
| 拉黑关系（任一方向）      | 403  |
| 已有 pending 邀请给同一人 | 409  |

### GET /api/v1/bookings/invites/sent — 我发出的邀请

返回当前用户发出的所有邀请，按 created_at 降序。

### GET /api/v1/bookings/invites/received — 我收到的邀请

返回当前用户收到的所有邀请，按 created_at 降序。查询时对 pending 且 play_date < today 的记录标记为 expired。

### GET /api/v1/bookings/invites/{invite_id} — 邀请详情

仅邀请双方可查看，否则 403。

### POST /api/v1/bookings/invites/{invite_id}/accept — 接受邀请

仅被邀请人可操作。执行顺序：

1. 校验 invite 状态为 pending
2. `invite.status` → `accepted`
3. 调用 `create_booking()` 创建 Booking（`min_ntrp` / `max_ntrp` 用双方实际 NTRP 的范围填充，纯记录用）
4. 双方自动加为 accepted 的 BookingParticipant
5. Booking 状态直接设为 confirmed
6. 自动创建 ChatRoom
7. `invite.booking_id` → 新 Booking 的 id
8. 通知发起人（`BOOKING_INVITE_ACCEPTED`）

### POST /api/v1/bookings/invites/{invite_id}/reject — 拒绝邀请

仅被邀请人可操作。`invite.status` → `rejected`，通知发起人（`BOOKING_INVITE_REJECTED`）。

## 通知

新增 3 个 `NotificationType` 枚举值：

| 枚举值                    | 触发时机     | 接收人   |
| ------------------------- | ------------ | -------- |
| `BOOKING_INVITE_RECEIVED` | 邀请发出时   | 被邀请人 |
| `BOOKING_INVITE_ACCEPTED` | 邀请被接受时 | 发起人   |
| `BOOKING_INVITE_REJECTED` | 邀请被拒绝时 | 发起人   |

## 过期机制

不使用定时任务。在查询 received 列表时，对 pending 且 `play_date < date.today()` 的邀请批量更新为 expired。单条查询（详情 / accept / reject）也做同样检查。

## 对现有代码的影响

### 新增文件

| 文件                             | 内容                                              |
| -------------------------------- | ------------------------------------------------- |
| `app/models/booking_invite.py`   | InviteStatus 枚举 + BookingInvite 模型            |
| `app/schemas/booking_invite.py`  | 请求/响应 schema                                  |
| `app/services/booking_invite.py` | create / accept / reject / list 业务逻辑          |
| `app/routers/booking_invite.py`  | 6 个 API endpoint                                 |
| Alembic migration                | 新建 booking_invites 表 + notification 枚举新增值 |

### 修改文件

| 文件                         | 变更                             |
| ---------------------------- | -------------------------------- |
| `app/models/notification.py` | NotificationType 新增 3 个枚举值 |
| `app/main.py`                | 注册 booking_invite router       |
| `app/i18n.py`                | 新增邀请相关翻译 key             |

### 不修改

`models/booking.py`、`services/booking.py`、`routers/bookings.py` 均不改动。accept 时调用现有的 `create_booking()` 和 `confirm_booking()` 复用全部约球逻辑。
