# Life Management API

**English** · [中文](#中文)

A REST API for personal finance snapshots, recurring reminders, and daily todos, with
Google Calendar and Telegram integrations.

It began as a PowerShell + JSON-file app I ran on my own machine. This is the rewrite:
a typed Python service with a relational schema, an authenticated HTTP API, and tests.

[![CI](https://github.com/starfish7982-crypto/LifeManagementAPI/actions/workflows/ci.yml/badge.svg)](https://github.com/starfish7982-crypto/LifeManagementAPI/actions/workflows/ci.yml)

**Live API docs:** `https://YOUR-APP.fly.dev/docs`

---

## What it does

| Area | Description |
|---|---|
| **Assets** | Monthly net-worth snapshots, each holding line items with a category and currency. Category totals are aggregated in SQL. |
| **Reminders** | One-time, monthly, or yearly. The next due date is computed, never stored. |
| **Todos** | Due dates, completion state, partial updates via `PATCH`. |
| **Today** | Aggregates open todos, reminders due today, and Google Calendar events into one response. |
| **Notify** | Pushes that summary to Telegram. Designed to be called by a daily scheduler. |

## Stack

Python 3.10+ · FastAPI · SQLAlchemy 2.0 · SQLite · Pydantic v2 · pytest · Docker · GitHub Actions

---

## Architecture

```
                    ┌──────────────────────────────┐
   X-API-Key ─────► │  FastAPI                     │
                    │                              │
                    │  routers/   HTTP layer       │
                    │  schemas.py request/response │
                    │  services/  logic + I/O      │
                    │  models.py  ORM              │
                    └───────┬───────────┬──────────┘
                            │           │
                     ┌──────▼─────┐  ┌──▼──────────────────┐
                     │  SQLite    │  │ Google Calendar iCal│
                     │            │  │ Telegram Bot API    │
                     └────────────┘  └─────────────────────┘
```

Four layers, each with one job. Routers do HTTP; schemas define the contract; services
hold logic and outbound I/O; models describe storage. The payoff is testability —
`services/recurrence.py` is a pure function, so every calendar edge case is tested with
no database and no HTTP.

---

## Running it

```bash
git clone https://github.com/starfish7982-crypto/LifeManagementAPI.git
cd LifeManagementAPI

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

uvicorn app.main:app --reload
```

That is the whole setup. No configuration file is required to start: the API key
defaults to `dev-key-change-me`, the database is created on first run, and both
integrations stay disabled until you configure them.

Open <http://127.0.0.1:8000/docs> for the interactive OpenAPI documentation.

```bash
pytest                      # 57 tests
pytest --cov=app            # 94% coverage
ruff check app tests        # lint
docker build -t life-management-api . && docker run -p 8000:8000 life-management-api
```

### Configuration

Copy `.env.example` to `.env` and edit. **Set a real `API_KEY` before deploying anywhere.**

| Variable | Required | Purpose |
|---|---|---|
| `API_KEY` | for deployment | Shared secret for the `X-API-Key` header |
| `DATABASE_URL` | no | Defaults to `sqlite:///./life.db` |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | no | Blank disables push notifications |
| `GOOGLE_CALENDAR_ICAL_URL` | no | Secret .ics URL; blank disables calendar |
| `CALENDAR_CACHE_TTL_SECONDS` | no | Default 900 |

---

## API

All routes except `/health` require `X-API-Key`.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | Unauthenticated liveness probe |
| `GET` `POST` | `/assets/snapshots` | Paginated list (capped at 200); create |
| `GET` `PUT` `DELETE` | `/assets/snapshots/{id}` | |
| `GET` | `/assets/snapshots/{id}/categories` | SQL `GROUP BY` aggregate |
| `GET` `POST` | `/reminders` | Filter by `active_only`, `due_within_days` |
| `GET` `PUT` `DELETE` | `/reminders/{id}` | |
| `GET` `POST` | `/todos` | Filter by `done`, `due_before` |
| `PATCH` `DELETE` | `/todos/{id}` | `PATCH` is partial |
| `GET` | `/today` | Local data joined with the calendar feed |
| `POST` | `/today/notify` | Push the summary to Telegram |

```bash
curl -X POST localhost:8000/assets/snapshots \
  -H "X-API-Key: dev-key-change-me" -H "Content-Type: application/json" \
  -d '{"month":"2026-03-01","items":[
        {"name":"Checking","category":"cash","amount":"4200.00"},
        {"name":"Brokerage","category":"investments","amount":"18500.50"}]}'
```

---

## Design decisions

**Money is `Numeric(14,2)`, never `float`.** Binary floating point cannot represent
0.01 exactly, and the error compounds across a summed portfolio. `total` stays a
`Decimal` all the way to JSON for the same reason.

**Snapshot months are normalised to the 1st.** A snapshot identifies a month, so
`2026-03-04` and `2026-03-28` must be the same record. Without normalisation the
`UNIQUE(month)` constraint would not mean what its name says.

**A duplicate month returns 409, not 400.** The request is well-formed; it conflicts
with existing state. The distinction tells a client whether retrying could ever help.

**`next_due` is computed, not stored.** A stored copy goes stale the moment someone
edits the recurrence rule. The cost is that `due_within_days` filters in Python instead
of SQL — acceptable at this scale, and the fix if it stopped being acceptable would be
a materialised column maintained by a trigger.

**Monthly reminders clamp, they do not skip.** "The 31st" in February means the 28th
(or 29th). Skipping the month entirely is the bug this avoids, and it is tested against
leap years.

**`PATCH` uses `exclude_unset`.** Otherwise toggling `done` would silently null the
`due_date` the client never mentioned. There is a regression test named after this.

**Retries are limited to timeouts and 5xx.** A Telegram 400 means the request itself is
wrong; retrying it three times burns rate limit and fails anyway.

**A failed notification never fails the request.** Delivery outcome is reported in the
response body; the write already succeeded and must not be reported as a 500.

**The calendar serves stale cache on upstream failure.** A calendar outage should
degrade the response, not empty it — an empty list is indistinguishable from "no events
today", which is a lie.

**API keys are compared with `secrets.compare_digest`.** `==` short-circuits on the
first differing byte and leaks the key prefix through response timing.

**Telegram messages are HTML-escaped.** `parse_mode=HTML` plus a todo titled
`<b>rent` would corrupt the message. Tested.

---

## Trade-offs and limits

Honest about what this is not:

- **SQLite, single writer.** Fine for one user. Concurrent writes would need Postgres —
  the SQLAlchemy layer is portable, only `DATABASE_URL` changes.
- **`create_all()` instead of migrations.** It cannot alter an existing table. Alembic
  is the correct next step and is the first thing I would add for a second user.
- **One shared API key, no per-user auth.** Multi-user needs real identity; the schema
  has no `user_id` column and adding one is not a small change.
- **Calendar cache is in-process.** Multiple instances each keep their own; Redis would
  be the fix.
- **iCal instead of the Google Calendar API.** No OAuth flow, no token storage, no
  Cloud project. The cost is read-only access to one calendar.

## Roadmap

- [ ] Alembic migrations
- [ ] Postgres support in CI (matrix build)
- [ ] Recurring todos generated from reminders
- [ ] Web UI consuming this API

## License

MIT

---
---

## 中文

[English](#life-management-api) · **中文**

個人資產快照、週期性提醒與每日待辦的 REST API，整合 Google Calendar 與 Telegram。

這個專案原本是我自己電腦上跑的 PowerShell + JSON 檔應用程式。這是重寫版本：具型別的
Python 服務，關聯式資料表、需驗證的 HTTP API，以及測試。

### 功能

| 區塊 | 說明 |
|---|---|
| **Assets** | 每月資產快照，底下是帶類別與幣別的項目。類別加總在 SQL 層用 `GROUP BY` 完成。 |
| **Reminders** | 單次、每月、每年。下次到期日是計算出來的，不儲存。 |
| **Todos** | 到期日、完成狀態，用 `PATCH` 做部分更新。 |
| **Today** | 把未完成待辦、今日到期提醒、Google 日曆事件合併成單一回應。 |
| **Notify** | 將上述摘要推播到 Telegram，設計給每日排程呼叫。 |

### 技術

Python 3.10+ · FastAPI · SQLAlchemy 2.0 · SQLite · Pydantic v2 · pytest · Docker · GitHub Actions

### 怎麼跑起來

```bash
git clone https://github.com/starfish7982-crypto/LifeManagementAPI.git
cd LifeManagementAPI

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

uvicorn app.main:app --reload
```

這樣就好，**不需要任何設定檔就能啟動**：API key 預設是 `dev-key-change-me`，資料庫在
第一次執行時自動建立，兩個外部整合在你設定之前都保持停用。

開 <http://127.0.0.1:8000/docs> 就有互動式 API 文件。

```bash
pytest                      # 57 個測試
pytest --cov=app            # 94% 覆蓋率
ruff check app tests        # 靜態檢查
```

### 設定

把 `.env.example` 複製成 `.env` 再編輯。**部署到任何地方之前一定要換掉 `API_KEY`。**

| 變數 | 必要 | 用途 |
|---|---|---|
| `API_KEY` | 部署時必要 | `X-API-Key` 標頭用的共享金鑰 |
| `DATABASE_URL` | 否 | 預設 `sqlite:///./life.db` |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | 否 | 留空即停用推播 |
| `GOOGLE_CALENDAR_ICAL_URL` | 否 | 日曆的秘密 .ics 網址；留空即停用 |
| `CALENDAR_CACHE_TTL_SECONDS` | 否 | 預設 900 秒 |

### 設計決策

**金額用 `Numeric(14,2)`，不用 `float`。** 二進位浮點數無法精確表示 0.01，誤差會在加總
時累積。`total` 一路保持 `Decimal` 到 JSON，理由相同。

**快照月份正規化到當月 1 號。** 一個快照代表一個月份，所以 `2026-03-04` 和 `2026-03-28`
必須是同一筆。不做正規化的話，`UNIQUE(month)` 這個約束就名不副實。

**月份重複回 409，不是 400。** 請求本身格式正確，衝突的是現有狀態。這個區別告訴呼叫端
重試有沒有意義。

**`next_due` 用算的，不儲存。** 一旦有人改了週期規則，儲存的副本立刻過期。代價是
`due_within_days` 必須在 Python 過濾而不是 SQL——在這個資料量下可以接受，真的不能接受時
的解法是加一個由 trigger 維護的實體化欄位。

**月提醒會 clamp，不會跳過。** 設在 31 號的提醒，二月是 28 號（閏年 29 號）。整個月跳過
才是要避免的 bug，而且有針對閏年的測試。

**`PATCH` 用 `exclude_unset`。** 否則只切換 `done` 會把呼叫端根本沒提到的 `due_date`
清成 null。有一個以此命名的回歸測試。

**只重試逾時和 5xx。** Telegram 回 400 代表請求本身有問題，重試三次只會消耗速率限制，
最後還是失敗。

**推播失敗絕不讓請求失敗。** 傳送結果寫在回應內容裡；資料早就寫入成功了，不該回 500。

**日曆上游失敗時回舊快取。** 日曆掛掉應該讓回應降級，而不是變空——空陣列跟「今天沒有
行程」在語意上無法區分，那等於說謊。

**API key 用 `secrets.compare_digest` 比對。** `==` 會在第一個不同的位元組短路，透過回應
時間洩漏金鑰前綴。

**Telegram 訊息做 HTML 跳脫。** `parse_mode=HTML` 加上一個叫 `<b>rent` 的待辦會讓訊息
壞掉。有測試。

### 取捨與限制

誠實說明這個專案不是什麼：

- **SQLite，單一寫入者。** 個人使用沒問題。要並行寫入就得換 Postgres——SQLAlchemy 那層
  是可移植的，只需要改 `DATABASE_URL`。
- **用 `create_all()` 而非 migration。** 它無法變更既有資料表。Alembic 是正確的下一步。
- **單一共享 API key，沒有使用者概念。** 多使用者需要真正的身分機制；目前 schema 沒有
  `user_id` 欄位，補上去不是小工程。
- **日曆快取在行程記憶體內。** 開多個 instance 各自持有一份，解法是 Redis。
- **用 iCal 而非 Google Calendar API。** 不需要 OAuth 流程、token 儲存或 Cloud 專案，
  代價是只能唯讀存取單一日曆。

### 授權

MIT
