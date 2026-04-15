# 社区赛事系统 (Event System) 设计文档

## 概述

社区赛事系统允许用户组织和参加网球赛事。支持淘汰赛（单打/双打）和循环赛，包含报名、自动抽签、结构化比分录入（双方确认制）、积分榜和签表展示。

**MVP 范围：** 淘汰赛（singles/doubles elimination）+ 循环赛（round_robin）。阶梯赛（Ladder）推迟到后续版本。

**费用策略：** 平台仅展示报名费和场地费金额，不介入任何资金流转，费用由球员线下自行解决。

**比赛时间和场地：** 平台不指定，由比赛双方自行协商决定。赛事只是组织框架。

**NTRP 影响：** MVP 不自动调整 NTRP 等级，仅记录赛事成绩。后续积累数据再设计评级算法。

---

## 1. 数据模型

### 1.1 Event（赛事主体）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| creator_id | FK → users.id | 赛事组织者 |
| name | String(100) | 赛事名称 |
| event_type | Enum | `singles_elimination` / `doubles_elimination` / `round_robin` |
| match_type | Enum | `singles` / `doubles`（复用 booking 的 MatchType） |
| min_ntrp | String(10) | 最低水平要求 |
| max_ntrp | String(10) | 最高水平要求 |
| gender_requirement | Enum | 复用 booking 的 GenderRequirement |
| max_participants | Integer | 人数上限 |
| games_per_set | Integer | 每盘局数（4 或 6） |
| num_sets | Integer | 几盘几胜（1 或 3） |
| match_tiebreak | Boolean | 决胜盘是否用抢十代替完整盘 |
| start_date | Date \| None | 建议开始日期（可选） |
| end_date | Date \| None | 建议结束日期（可选） |
| registration_deadline | DateTime | 报名截止时间 |
| entry_fee | Integer \| None | 报名费（展示用，不走平台） |
| description | Text \| None | 描述/规则说明 |
| status | Enum | `draft` / `open` / `in_progress` / `completed` / `cancelled` |
| created_at | DateTime | |
| updated_at | DateTime | |

### 1.2 EventParticipant（参赛者）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| event_id | FK → events.id | |
| user_id | FK → users.id | |
| seed | Integer \| None | 种子排位（抽签后填入） |
| group_name | String(10) \| None | 循环赛分组标记（"A"/"B"等），淘汰赛为 null |
| team_name | String(10) \| None | 双打队伍标记（"T1"/"T2"等），单打为 null |
| status | Enum | `registered` / `confirmed` / `withdrawn` / `eliminated` |
| joined_at | DateTime | |

UniqueConstraint(event_id, user_id)

### 1.3 EventMatch（单场比赛）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| event_id | FK → events.id | |
| round | Integer | 轮次（淘汰赛：1=首轮, 2=第二轮...；循环赛：轮次编号） |
| match_order | Integer | 本轮内的场序（用于签表位置） |
| player_a_id | FK → users.id \| None | 可空（BYE 或待定） |
| player_b_id | FK → users.id \| None | 可空（BYE 或待定） |
| winner_id | FK → users.id \| None | 比赛完成后填入 |
| group_name | String(10) \| None | 循环赛所属分组 |
| status | Enum | `pending` / `submitted` / `confirmed` / `disputed` / `walkover` |
| submitted_by | FK → users.id \| None | 谁先提交了比分 |
| confirmed_at | DateTime \| None | |
| created_at | DateTime | |

### 1.4 EventSet（每盘比分）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| match_id | FK → event_matches.id | |
| set_number | Integer | 第几盘（1, 2, 3） |
| score_a | Integer | 选手A局数 |
| score_b | Integer | 选手B局数 |
| tiebreak_a | Integer \| None | 抢七/抢十 A 得分 |
| tiebreak_b | Integer \| None | 抢七/抢十 B 得分 |

UniqueConstraint(match_id, set_number)

---

## 2. 赛事生命周期

### 2.1 状态流转

```
draft → open → in_progress → completed
  │       │         │
  └───────┴─────────┴──→ cancelled
```

| 转换 | 触发者 | 条件 |
|------|--------|------|
| draft → open | 创建者 | 发布赛事，开放报名 |
| open → in_progress | 创建者 | 报名截止、参赛人数达标，触发抽签 |
| in_progress → completed | 系统 | 所有 EventMatch 的 winner_id 全部填入 |
| 任意 → cancelled | 创建者 | 随时可取消，通知所有参赛者 |

### 2.2 最低参赛人数

- 淘汰赛（singles/doubles elimination）：≥ 4 人
- 循环赛（round_robin）：≥ 3 人

### 2.3 报名流程

1. 赛事状态 `open` 时可报名
2. 校验：信用分 ≥ 80、NTRP 在范围内、性别符合、未被创建者拉黑、人数未满
3. 报名后 `EventParticipant.status = registered`
4. 创建者可在报名截止前移除参赛者

---

## 3. 抽签与对阵生成

### 3.1 种子排位

按参赛者 NTRP 降序排列（使用现有 `_ntrp_to_float()`），NTRP 相同按信用分降序，仍相同则随机。排好后写入 `EventParticipant.seed`。

### 3.2 淘汰赛签表生成

1. 参赛人数不足 2 的幂次时用 BYE 补齐（如 5 人 → 8，3 个 BYE）
2. 种子分配：1 号顶部，2 号底部，3/4 号分别在上下半区中间，其余随机
3. BYE 分配给高种子选手，首轮自动晋级
4. BYE 场次：`player_b_id = None`，`status = confirmed`，`winner_id = player_a_id`
5. 后续轮次创建空壳 EventMatch（player_a/b 为 null），前一轮胜者确认后自动填入

### 3.3 循环赛分组 + 对阵

1. 蛇形分组：按种子号 S 形分配。如 8 人分 2 组 — A 组：1,4,5,8；B 组：2,3,6,7
2. 每组用轮转法生成全部轮次对阵
3. 奇数人时每轮一人轮空

### 3.4 双打处理

双打赛事中每人独立报名，用 `EventParticipant.team_name` 标记队伍（"T1"/"T2"等）。`EventMatch.player_a_id / player_b_id` 指向队伍的队长（首个报名者），队友通过相同 team_name 关联查询。

---

## 4. 比分录入与确认

### 4.1 录入流程

1. 任一方提交比分，创建 EventSet 记录（每盘一条）
2. 系统根据赛制配置验证比分合法性
3. 验证通过：`EventMatch.status = submitted`，`submitted_by` 记录提交者
4. 系统根据盘数胜负自动计算 `winner_id`

### 4.2 确认流程

1. 对方收到通知
2. **确认** → `status = confirmed`，`confirmed_at` 写入
3. **有异议** → `status = disputed`，通知组织者裁决
4. **24h 未响应** → 系统自动确认

### 4.3 组织者权限

- 可直接录入/修改任何 EventMatch 比分（不需要双方确认）
- 可裁决 disputed 状态的比赛

### 4.4 确认后触发

**淘汰赛：**
- 胜者自动填入下一轮 EventMatch
- 下一轮两个位置都填满时通知双方
- 最后一场确认 → 赛事 `completed`

**循环赛：**
- 更新该组积分榜（胜 3 分、负 0 分）
- 所有组内比赛完成 → 赛事 `completed`

### 4.5 比分验证规则

**games_per_set = 6 时：**

| 情况 | 合法比分 | 说明 |
|------|---------|------|
| 正常胜 | 6-0 到 6-4 | 达到 games_per_set，领先 ≥ 2 |
| 抢七 | 7-6 | 必须附 tiebreak 分数 |

**games_per_set = 4 时：**

| 情况 | 合法比分 |
|------|---------|
| 正常胜 | 4-0 到 4-2 |
| 抢七 | 5-4 + tiebreak |

**match_tiebreak = true 的决胜盘：** EventSet 记录 score_a=1, score_b=0（或 0-1），tiebreak_a/tiebreak_b 记录实际抢十比分。

### 4.6 弃权（Walkover）

触发：对手或组织者提交"对方缺席"。

处理：
- `EventMatch.status = walkover`
- `winner_id` = 到场方
- EventSet 记录比分 0-0（表示未实际进行）
- 缺席方触发信用分扣罚（复用 `apply_credit_change()`，走约球同样的扣分规则）
- 缺席方 `EventParticipant.status = withdrawn`

确认流程与比分录入相同（一方提交，对方确认或组织者裁决），防止恶意举报。

---

## 5. 通知

### 5.1 新增 NotificationType

| 类型 | 触发时机 |
|------|---------|
| `EVENT_REGISTRATION_OPEN` | 赛事发布（open） |
| `EVENT_JOINED` | 有人报名，通知组织者 |
| `EVENT_STARTED` | 赛事开始，通知参赛者对阵安排 |
| `EVENT_MATCH_READY` | 对阵双方就位，通知双方可以约球 |
| `EVENT_SCORE_SUBMITTED` | 对手提交比分，通知确认 |
| `EVENT_SCORE_CONFIRMED` | 比分确认完成 |
| `EVENT_SCORE_DISPUTED` | 比分有异议，通知组织者 |
| `EVENT_WALKOVER` | 对方被判弃权 |
| `EVENT_ELIMINATED` | 淘汰赛中被淘汰 |
| `EVENT_COMPLETED` | 赛事结束 |
| `EVENT_CANCELLED` | 赛事取消 |

---

## 6. 聊天集成

- `ChatRoom` 新增 `event_id: FK → events.id | None`（可空，unique），与 `booking_id` 并列
- 赛事开始时（open → in_progress）自动创建群聊，所有参赛者加入
- 房间名 = 赛事名称
- 赛事取消/完成 → 群聊 `is_readonly = True`

---

## 7. API 端点

### 7.1 赛事 CRUD

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/events` | 创建赛事（status=draft） |
| GET | `/api/v1/events` | 赛事列表（筛选：status/event_type） |
| GET | `/api/v1/events/my` | 我创建的 + 我参加的赛事 |
| GET | `/api/v1/events/{id}` | 赛事详情 |
| PATCH | `/api/v1/events/{id}` | 修改赛事（仅 draft/open） |
| POST | `/api/v1/events/{id}/publish` | draft → open |
| POST | `/api/v1/events/{id}/start` | open → in_progress，触发抽签 + 建群 |
| POST | `/api/v1/events/{id}/cancel` | 取消赛事 |

### 7.2 报名

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/events/{id}/join` | 报名 |
| POST | `/api/v1/events/{id}/withdraw` | 退出（in_progress 前） |
| DELETE | `/api/v1/events/{id}/participants/{user_id}` | 组织者移除参赛者 |

### 7.3 比赛与比分

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/events/{id}/matches` | 对阵列表（筛选：round/group） |
| GET | `/api/v1/events/{id}/bracket` | 淘汰赛签表（树状结构） |
| GET | `/api/v1/events/{id}/standings` | 循环赛积分榜 |
| POST | `/api/v1/events/matches/{match_id}/score` | 提交比分 |
| POST | `/api/v1/events/matches/{match_id}/confirm` | 确认比分 |
| POST | `/api/v1/events/matches/{match_id}/dispute` | 比分异议 |
| POST | `/api/v1/events/matches/{match_id}/walkover` | 提交对方缺席 |
| PATCH | `/api/v1/events/matches/{match_id}/score` | 组织者修改比分/裁决 |

### 7.4 端点规则

- 所有端点需登录（CurrentUser）
- 创建赛事需信用分 ≥ 80
- 修改/取消/开始/移除参赛者仅组织者
- 比分提交/确认仅比赛双方
- 组织者修改比分不需要确认
- 列表排序：理想球友创建的优先，然后按 registration_deadline

---

## 8. 文件结构

### 8.1 新增文件

| 文件 | 说明 |
|------|------|
| `app/models/event.py` | Event, EventParticipant, EventMatch, EventSet + 枚举 |
| `app/services/event.py` | 赛事核心逻辑 |
| `app/routers/events.py` | API 端点 |
| `app/schemas/event.py` | 请求/响应 schema |
| `tests/test_events.py` | 测试 |
| Alembic migration | 4 张新表 + chat_rooms.event_id + notification 枚举值 |

### 8.2 修改现有文件

| 文件 | 改动 |
|------|------|
| `app/models/notification.py` | NotificationType 新增 11 个枚举值 |
| `app/models/chat.py` | ChatRoom 新增 event_id 字段 |
| `app/models/__init__.py` | 导入 event 模型 |
| `app/services/chat.py` | 新增 create_event_chat_room() |
| `app/main.py` | 注册 events router |
| `app/i18n.py` | 新增赛事相关 i18n key |

### 8.3 不改动

booking、review、credit、matching 等现有模块完全不动。信用分扣罚复用 `apply_credit_change()`。
