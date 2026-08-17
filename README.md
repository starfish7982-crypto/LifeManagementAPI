# Life Management API

**English** · [中文](#中文)

A REST API for personal finance snapshots, recurring reminders, daily todos, custom
lists, meal planning and trip logistics — with Google Calendar and Telegram
integrations, and a React front end served from the same origin.

It began as a PowerShell + JSON-file app I ran on my own machine. This is the rewrite:
a typed Python service with a relational schema, per-user authentication, migrations,
and tests.

[![CI](https://github.com/starfish7982-crypto/LifeManagementAPI/actions/workflows/ci.yml/badge.svg)](https://github.com/starfish7982-crypto/LifeManagementAPI/actions/workflows/ci.yml)

**Live app:** <https://life-management-api-jkje.onrender.com/app/>
**Live API docs:** <https://life-management-api-jkje.onrender.com/docs>
**Health check:** <https://life-management-api-jkje.onrender.com/health>

Hosted on Render's free tier, which idles the instance after ~15 minutes without
traffic — the first request may take 30-50 seconds while it wakes up.

**Registration is closed on the deployed instance.** The API docs are public and the
code is open, but account creation is gated behind `ALLOW_REGISTRATION`, which is off
by default. Run your own copy to use it — the setup below takes a few minutes.

---

## Where this is up to

The first published version was an API-only service behind a single shared API key,
with five areas and no migrations. Everything in that description still holds for the
shape of the code; what follows is what has changed since, kept here because the older
description is still what most of the write-ups about this project refer to.

| Then | Now |
|---|---|
| One shared `X-API-Key` header | Per-account sign-up, JWT access tokens, Argon2id password hashing |
| No `user_id`; one dataset for the whole service | Every table is scoped to an account and filtered on every query |
| `create_all()` at startup | 12 Alembic migrations; `alembic upgrade head` runs before the server starts |
| Assets · Reminders · Todos · Today · Notify | …plus Lists, Ideas, Grocery, Travel, and per-user Settings |
| API only | React 18 + TypeScript UI, built by Vite, served from `/app` on the same origin |
| Integrations configured server-wide via env vars | Configured per account and stored in `user_settings` |
| 122 tests | 182 tests, 93% statement coverage |

The three roadmap items that motivated most of this — migrations, real per-user auth,
and a web UI — are done. What is still open is listed under
[Trade-offs and limits](#trade-offs-and-limits).

---

## What it does

| Area | Description |
|---|---|
| **Assets** | Monthly net-worth snapshots, each holding line items with a category and currency. Category totals are aggregated in SQL. A savings goal with a purpose and next step sits alongside. |
| **Reminders** | One-time, monthly, or yearly. The next due date is computed, never stored. |
| **Todos** | Due dates, completion state, lanes and manual ordering, partial updates via `PATCH`. |
| **Today** | Aggregates open todos, reminders due today, and Google Calendar events into one response. |
| **Notify** | Pushes that summary to Telegram. Designed to be called by a daily scheduler. |
| **Lists** | User-defined tables — you name the columns, the rows are JSON. Used for fixed monthly costs, budgets, warranties, addresses. Reorderable. |
| **Ideas** | A single scratch list for things that are not yet a todo. |
| **Grocery** | Meal ideas by category, recipes with ingredients and steps, and a shopping list. |
| **Travel** | A trip with lodgings, a packing list, card benefits with expiry dates, and expenses. Lodging details can be suggested from calendar events. |
| **Settings** | Per-account Telegram and Google Calendar configuration, with a test-send endpoint. |

## Stack

**Backend** — Python 3.10+ · FastAPI · SQLAlchemy 2.0 · Alembic · Postgres / SQLite ·
Pydantic v2 · JWT (PyJWT) + Argon2id (pwdlib) · pytest

**Frontend** — React 18 · TypeScript (strict) · Vite

**Delivery** — Docker (multi-stage) · Render · Neon · GitHub Actions

**Optional** — Tesseract OCR (receipt scanning; the endpoint degrades to a review-only
upload when the binary is absent)

---

## Architecture

```
   Authorization: ─────► ┌──────────────────────────────┐
   Bearer <JWT>          │  FastAPI                     │
                         │                              │
                         │  routers/      HTTP layer    │
                         │  schemas.py    contract      │
                         │  dependencies. per-user wiring│
                         │  services/     logic + I/O   │
                         │  models.py     ORM           │
                         └───────┬───────────┬──────────┘
                                 │           │
                          ┌──────▼─────┐  ┌──▼──────────────────┐
                          │  Postgres  │  │ Google Calendar iCal│
                          │  (SQLite   │  │ Telegram Bot API    │
                          │   locally) │  │ (per account)       │
                          └────────────┘  └─────────────────────┘
```

Layers, each with one job. Routers do HTTP; schemas define the contract; services hold
logic and outbound I/O; models describe storage. The payoff is testability —
`services/recurrence.py` is a pure function, so every calendar edge case is tested with
no database and no HTTP.

`dependencies.py` is where accounts meet integrations. Calendar and Telegram clients are
built per request from the caller's own `user_settings` row rather than from application
config. They used to be `@lru_cache` singletons built from environment variables, which
was fine with one dataset and became a leak the moment accounts existed: any signed-in
user calling `/today` saw whichever calendar the operator had configured.

Nothing above the `models.py` line knows which database is underneath. That is what let
the deployment move from SQLite to Postgres by changing one environment variable.

The React app in `web/` is built by Vite and served by this same process from `/app`,
so the browser never makes a cross-origin request and CORS is off by default. That
couples the two deploys together — a CSS change rebuilds the whole image — which is a
real cost, paid for a setup with one origin, one cold start, and no CORS configuration
to get wrong.

---

## Running it

```bash
git clone https://github.com/starfish7982-crypto/LifeManagementAPI.git
cd LifeManagementAPI

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

uvicorn app.main:app --reload
```

That is the whole setup. No configuration file is required to start: the database is
created on first run against local SQLite, and both integrations stay disabled until an
account configures them.

One thing does need setting, because it defaults to off: account creation.

```bash
ALLOW_REGISTRATION=true uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/docs> for the interactive OpenAPI documentation, then
`POST /auth/register` to create your account. Once you have one, drop the variable —
the app keeps working and nobody else can sign up.

That serves the API. The UI is a separate build:

```bash
cd web
npm install
npm run build     # tsc --noEmit, then vite build into web/dist
```

`app/main.py` mounts `web/dist` at `/app`, so once it is built the whole thing is on
one origin at <http://127.0.0.1:8000>. While working on the UI, `npm run dev` is
faster — Vite serves it on :5173 with hot reload and proxies the API paths through to
:8000, so the browser still sees a single origin and the dev setup exercises the same
same-origin behaviour as production.

```bash
pytest                              # 182 tests
pytest --cov=app                    # 93% coverage
ruff check app tests alembic scripts
cd web && npm run typecheck && npm run lint
docker build -t life-management-api . && docker run -p 8000:8000 life-management-api
```

### Configuration

Copy `.env.example` to `.env` and edit. **Set a real `JWT_SECRET` before deploying
anywhere** — anyone holding it can mint a token for any account. Generate one with
`openssl rand -hex 32`.

| Variable | Required | Purpose |
|---|---|---|
| `JWT_SECRET` | for deployment | Signs access tokens. The app refuses to boot if this is still the development default in front of a non-SQLite database |
| `ALLOW_REGISTRATION` | no | **Defaults to false.** `POST /auth/register` answers 403 until this is true. Existing accounts are unaffected |
| `ACCESS_TOKEN_TTL_MINUTES` | no | Default 720 (12 hours) |
| `DATABASE_URL` | no | Defaults to `sqlite:///./life.db`; set to a Postgres URL when deployed |
| `CORS_ORIGINS` | no | Comma-separated origins. Blank by default, and blank is correct while the UI ships from this same process. Never `*` — requests carry an `Authorization` header |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | no | Fallback only; accounts normally set their own in the app |
| `GOOGLE_CALENDAR_ICAL_URL` | no | Legacy fallback. The calendar feed is read strictly from the account's own settings |
| `CALENDAR_CACHE_TTL_SECONDS` | no | Default 900 |

Telegram and Google Calendar are configured per account through `PATCH /settings` in
the running app, not through the environment. Those values live in the `user_settings`
table.

### Deployment

`render.yaml` describes the service as a Render Blueprint: create it from the Render
dashboard via **New +** → **Blueprint**, pointed at this repository. The image is the
same `Dockerfile` used locally. Pushes to `main` redeploy automatically.

Two properties of free-tier container hosting drive the configuration:

- **The filesystem is ephemeral.** A SQLite file inside the container is erased on every
  restart and redeploy, so a deployed instance needs `DATABASE_URL` pointing at managed
  Postgres. Neon's free tier does not expire — note that Render's own free Postgres
  does, 30 days after creation. Paste the provider's connection string in verbatim;
  `app/database.py` rewrites `postgres://` and `postgresql://` to the psycopg 3 driver
  this project installs.
- **The instance sleeps when idle.** After ~15 minutes without traffic the first request
  back pays a 30-50 second cold start. The engine is configured with `pool_pre_ping` so
  that request does not fail on a connection the database closed while the app slept.

Schema changes are applied by `docker-entrypoint.sh`, which runs `alembic upgrade head`
and only then starts the server — a failed migration aborts the deploy instead of
leaving the API serving against a schema the code does not expect. See
`alembic/README.md` for why this is not Render's `preDeployCommand`.

`JWT_SECRET` is declared with `generateValue: true`, so Render mints a random secret on
first apply and reuses it across deploys. No secret is ever committed to this repository,
and the app refuses to boot if it finds the development default in front of a real
database.

---

## API

Every route except `/health`, `/auth/register` and `/auth/login` requires
`Authorization: Bearer <token>`. All rows are scoped to the account the token
identifies.

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | Unauthenticated liveness probe |
| `GET` | `/auth/config` | Unauthenticated; tells the sign-in screen whether to offer sign-up |
| `POST` | `/auth/register` `/auth/login` | Register is 403 unless `ALLOW_REGISTRATION`. Login is the OAuth2 password flow (form-encoded) and returns a JWT |
| `GET` `POST` | `/auth/me` `/auth/password` | Current account; change password (returns a fresh token) |
| `GET` `POST` | `/assets/snapshots` | Paginated list (capped at 200); create |
| `GET` `PUT` `DELETE` | `/assets/snapshots/{id}` | |
| `GET` | `/assets/snapshots/{id}/categories` | SQL `GROUP BY` aggregate |
| `GET` `PUT` `DELETE` | `/assets/goal` | Savings goal, purpose, next step |
| `GET` `POST` | `/reminders` | Filter by `active_only`, `due_within_days` |
| `GET` `POST` | `/todos` | Filter by `done`, `due_before`; `PUT /todos/order` reorders |
| `PATCH` `DELETE` | `/todos/{id}` | `PATCH` is partial |
| `GET` `POST` | `/lists` | User-defined columns; `PUT /lists/order` |
| `POST` `PUT` `DELETE` | `/lists/{id}/items` | Rows are JSON matching the list's columns |
| `GET` `POST` | `/ideas` | |
| `GET` `POST` | `/grocery/meal-ideas` `/grocery/recipes` `/grocery/shopping` | |
| `GET` `PUT` `DELETE` | `/travel` | The trip; lodgings, packing, benefits, expenses hang off it |
| `POST` | `/travel/expenses/scan` | Receipt OCR; falls back to review-only without Tesseract |
| `GET` | `/travel/lodging-suggestions` | Parses lodging details out of calendar events |
| `GET` `PATCH` | `/settings` | Per-account Telegram and Calendar configuration |
| `POST` | `/settings/telegram/test` | Send a test message |
| `GET` | `/today` | Local data joined with the calendar feed |
| `POST` | `/today/notify` | Push the summary to Telegram |


## Design decisions

**Money is `Numeric(14,2)`, never `float`.** Binary floating point cannot represent
0.01 exactly, and the error compounds across a summed portfolio. `total` stays a
`Decimal` all the way to JSON for the same reason.

**Passwords are Argon2id via pwdlib.** passlib has had no release since 2020 and breaks
against bcrypt 4.1+; `PasswordHash.recommended()` picks Argon2id and keeps that choice
in one place.

**There is no refresh token.** A second token type roughly doubles the auth surface, and
for a personal tool the cost of signing in again each day is lower than the cost of
getting refresh-token rotation subtly wrong.

**Registration is closed by default, and the default is the security property.** A
personal deployment sits on a public URL; an open endpoint means any stranger who finds
it takes a share of a free instance and of a 0.5 GB database. Defaulting to open and
relying on the deployment to close it has the failure mode backwards — a forgotten
setting should mean "nobody can sign up", not "anybody can". The check runs before the
username lookup, so a closed instance cannot be used to find out which names are taken.

**Integrations are per account, with no server-wide calendar fallback.** A fallback is
surprising in a personal app: it can make a newly created account appear to have
somebody else's calendar before the owner connects their own.

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

**Built assets are cached forever, `index.html` never.** Vite writes a content hash into
every asset filename, so those can never change and are served `immutable`. `index.html`
names them, so a cached copy is how a browser ends up running last week's JavaScript.

**Telegram messages are HTML-escaped.** `parse_mode=HTML` plus a todo titled
`<b>rent` would corrupt the message. Tested.

---

## Trade-offs and limits

Honest about what this is not:

- **The test suite runs on SQLite; production is Postgres.** Migrations are exercised
  against both in CI, but the query paths are only covered on SQLite. A Postgres matrix
  build is the fix and is still on the list.
- **Telegram bot tokens are stored in plaintext.** Same exposure as `DATABASE_URL`:
  anyone who can read the database can read them, and the token grants only the ability
  to post to one chat. A service holding tokens for many people would encrypt them with
  a key the database does not have.
- **Receipt images are stored as bytes in Postgres**, up to 8 MB each. That is fine for
  a handful and wrong at volume — a 0.5 GB free-tier database holds roughly sixty
  full-size receipts. Object storage is the fix if receipts become routine.
- **The calendar cache is in-process**, keyed by feed URL and bounded at 64 entries.
  Multiple instances each keep their own; Redis would be the fix.
- **iCal instead of the Google Calendar API.** No OAuth flow, no token storage, no Cloud
  project. The cost is read-only access to one calendar.
- **Migrations run at container start, not pre-deploy.** Render's `preDeployCommand` is
  the right place and is a paid-plan feature. With one free-tier instance there is no
  race; the moment this scales, that line moves.
- **The free tier cold-starts.** The first request after idling waits 30-50 seconds.
  That is a hosting-plan limit rather than a defect in the code, but the distinction is
  invisible to a real user; a paid plan or a keep-alive ping fixes it.

## Roadmap

- [x] Alembic migrations
- [x] Per-user accounts and authentication
- [x] Web UI consuming this API
- [ ] Postgres in CI (matrix build), so the deployed query paths are covered by tests
- [ ] Recurring todos generated from reminders
- [ ] Receipt images in object storage rather than in the database

## License

MIT

---
---

## 中文

[English](#life-management-api) · **中文**

個人資產快照、週期性提醒、每日待辦、自訂清單、備餐規劃與旅遊行程的 REST API，
整合 Google Calendar 與 Telegram，並附一個同源提供的 React 前端。

這個專案原本是我自己電腦上跑的 PowerShell + JSON 檔應用程式。這是重寫版本：具型別的
Python 服務，關聯式資料表、每位使用者獨立的驗證機制、schema migration，以及測試。

**線上應用：**<https://life-management-api-jkje.onrender.com/app/>
**線上 API 文件：**<https://life-management-api-jkje.onrender.com/docs>
**健康檢查：**<https://life-management-api-jkje.onrender.com/health>

部署在 Render 免費方案，約 15 分鐘無流量會休眠，第一個請求可能要等 30-50 秒喚醒。

**線上這個部署的註冊功能是關閉的。** API 文件公開、程式碼開源，但建立帳號受
`ALLOW_REGISTRATION` 控制，而它預設是關的。想使用請自行架設一份，下面的步驟只要幾分鐘。

---

### 目前進度

最初發布的版本是純 API 服務，用單一共享 API key，只有五個功能區塊，也沒有 migration。
那份說明描述的程式結構到現在依然成立；以下列出的是之後的變動——之所以保留在這裡，是因為
目前多數關於這個專案的說明仍是引用舊版描述。

| 之前 | 現在 |
|---|---|
| 單一共享的 `X-API-Key` 標頭 | 每個帳號各自註冊、JWT access token、Argon2id 密碼雜湊 |
| 沒有 `user_id`，全服務共用一份資料 | 每張表都歸屬於帳號，每次查詢都會過濾 |
| 啟動時跑 `create_all()` | 12 個 Alembic migration；伺服器啟動前先跑 `alembic upgrade head` |
| Assets · Reminders · Todos · Today · Notify | ……再加上 Lists、Ideas、Grocery、Travel 與每位使用者的 Settings |
| 只有 API | React 18 + TypeScript 前端，由 Vite 建置，掛在同源的 `/app` |
| 整合設定用環境變數、全服務共用 | 改為每個帳號各自設定，存在 `user_settings` 表 |
| 122 個測試 | 182 個測試，93% 敘述覆蓋率 |

當初待辦清單上驅動了大部分改動的三件事——migration、真正的多使用者驗證、網頁前端——
都已完成。還沒解決的部分列在[取捨與限制](#取捨與限制)。

---

### 功能

| 區塊 | 說明 |
|---|---|
| **Assets** | 每月資產快照，底下是帶類別與幣別的項目。類別加總在 SQL 層用 `GROUP BY` 完成。旁邊還有一個含用途與下一步的存錢目標。 |
| **Reminders** | 單次、每月、每年。下次到期日是計算出來的，不儲存。 |
| **Todos** | 到期日、完成狀態、分道與手動排序，用 `PATCH` 做部分更新。 |
| **Today** | 把未完成待辦、今日到期提醒、Google 日曆事件合併成單一回應。 |
| **Notify** | 將上述摘要推播到 Telegram，設計給每日排程呼叫。 |
| **Lists** | 使用者自訂的表格——欄位自己命名，每列是 JSON。用來記每月固定支出、預算、產品保固、地址等。可重新排序。 |
| **Ideas** | 一份暫存清單，放還沒成形為待辦的想法。 |
| **Grocery** | 依類別分類的備餐點子、含食材與步驟的食譜，以及購物清單。 |
| **Travel** | 一趟行程，底下有住宿、打包清單、含到期日的信用卡權益，以及支出。住宿細節可以從日曆事件推測填入。 |
| **Settings** | 每個帳號各自的 Telegram 與 Google Calendar 設定，並有測試發送端點。 |

### 技術

**後端** — Python 3.10+ · FastAPI · SQLAlchemy 2.0 · Alembic · Postgres / SQLite ·
Pydantic v2 · JWT（PyJWT）+ Argon2id（pwdlib）· pytest

**前端** — React 18 · TypeScript（strict）· Vite

**部署** — Docker（多階段建置）· Render · Neon · GitHub Actions

**選用** — Tesseract OCR（收據掃描；系統上沒有這個執行檔時，端點會降級成只上傳待人工檢視）

---

### 架構

```
   Authorization: ─────► ┌──────────────────────────────┐
   Bearer <JWT>          │  FastAPI                     │
                         │                              │
                         │  routers/       HTTP 層      │
                         │  schemas.py     介面契約     │
                         │  dependencies.  每使用者接線 │
                         │  services/      邏輯與對外 IO│
                         │  models.py      ORM          │
                         └───────┬───────────┬──────────┘
                                 │           │
                          ┌──────▼─────┐  ┌──▼──────────────────┐
                          │  Postgres  │  │ Google Calendar iCal│
                          │ （本機用   │  │ Telegram Bot API    │
                          │   SQLite） │  │ （每個帳號各自）    │
                          └────────────┘  └─────────────────────┘
```

分層，每層只做一件事。Routers 處理 HTTP；schemas 定義介面契約；services 放邏輯與對外
I/O；models 描述儲存。好處是可測試性——`services/recurrence.py` 是純函式，所以每個日期
邊界case 都能在沒有資料庫、沒有 HTTP 的情況下測試。

`dependencies.py` 是帳號與外部整合交會的地方。Calendar 與 Telegram 的 client 是依照
呼叫者自己的 `user_settings` 逐請求建立，而不是從應用程式設定建立。它們原本是用
`@lru_cache` 從環境變數建的單例——在只有一份資料時沒問題，但有了帳號之後就變成資料外洩：
任何登入的使用者呼叫 `/today`，看到的都是維運者設定的那個日曆。

`models.py` 這條線以上的程式碼都不知道底下是哪種資料庫。這正是部署能夠只改一個環境變數
就從 SQLite 換成 Postgres 的原因。

`web/` 裡的 React 應用由 Vite 建置，並由同一個行程掛在 `/app` 提供，所以瀏覽器從不發出
跨來源請求，CORS 預設關閉。代價是兩邊的部署被綁在一起——改一行 CSS 也要重建整個
image——換來的是單一來源、單一冷啟動，以及沒有 CORS 設定可以搞砸。

---

### 怎麼跑起來

```bash
git clone https://github.com/starfish7982-crypto/LifeManagementAPI.git
cd LifeManagementAPI

python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

uvicorn app.main:app --reload
```

這樣就好，**不需要任何設定檔就能啟動**：資料庫在第一次執行時對本機 SQLite 自動建立，
兩個外部整合在帳號自行設定之前都保持停用。

只有一件事需要特別設定，因為它預設是關的：建立帳號。

```bash
ALLOW_REGISTRATION=true uvicorn app.main:app --reload
```

開 <http://127.0.0.1:8000/docs> 就有互動式 API 文件，然後用 `POST /auth/register`
建立你的帳號。有帳號之後把這個變數拿掉即可——app 照常運作，而別人無法註冊。

這樣會啟動 API。前端要另外建置：

```bash
cd web
npm install
npm run build     # 先跑 tsc --noEmit，再 vite build 到 web/dist
```

`app/main.py` 會把 `web/dist` 掛在 `/app`，所以建置完之後整個 app 都在
<http://127.0.0.1:8000> 這一個來源底下。開發前端時用 `npm run dev` 比較快——Vite 在
:5173 提供熱重載，並把 API 路徑代理到 :8000，瀏覽器仍然只看到單一來源，開發環境跟正式
環境的同源行為一致。

```bash
pytest                              # 182 個測試
pytest --cov=app                    # 93% 覆蓋率
ruff check app tests alembic scripts
cd web && npm run typecheck && npm run lint
docker build -t life-management-api . && docker run -p 8000:8000 life-management-api
```

### 設定

把 `.env.example` 複製成 `.env` 再編輯。**部署到任何地方之前一定要設一個真的
`JWT_SECRET`**——拿到這個值的人可以偽造任何帳號的 token。用
`openssl rand -hex 32` 產生。

| 變數 | 必要 | 用途 |
|---|---|---|
| `JWT_SECRET` | 部署時必要 | 簽發 access token。當資料庫不是本機 SQLite 而這個值還是開發預設值時，程式會拒絕啟動 |
| `ALLOW_REGISTRATION` | 否 | **預設 false。** 在設成 true 之前，`POST /auth/register` 一律回 403。既有帳號不受影響 |
| `ACCESS_TOKEN_TTL_MINUTES` | 否 | 預設 720（12 小時） |
| `DATABASE_URL` | 否 | 預設 `sqlite:///./life.db`；部署時改指向 Postgres |
| `CORS_ORIGINS` | 否 | 逗號分隔的來源清單。預設留空，而在前端由同一個行程提供時，留空就是正確的。絕不要填 `*`——請求帶著 `Authorization` 標頭 |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | 否 | 只作為後備；帳號通常在 app 裡設定自己的 |
| `GOOGLE_CALENDAR_ICAL_URL` | 否 | 舊版後備。日曆來源嚴格只讀取帳號自己的設定 |
| `CALENDAR_CACHE_TTL_SECONDS` | 否 | 預設 900 秒 |

Telegram 與 Google Calendar 是在執行中的 app 裡透過 `PATCH /settings` 依帳號設定的，
不是靠環境變數。那些值存在 `user_settings` 表。

### 部署

`render.yaml` 是 Render Blueprint 設定檔：在 Render 後台選 **New +** → **Blueprint**，
指向這個 repo 即可建立服務，用的是跟本機一樣的 `Dockerfile`。推送到 `main` 會自動重新部署。

免費方案的兩個特性決定了上面的設定：

- **檔案系統是暫時的。** 容器裡的 SQLite 檔在每次重啟與重新部署後都會消失，所以部署版本的
  `DATABASE_URL` 必須指向託管的 Postgres。Neon 的免費方案不會過期——要注意 Render 自己的
  免費 Postgres 會，建立 30 天後就到期。供應商給的連線字串直接貼上即可，
  `app/database.py` 會把 `postgres://` 與 `postgresql://` 改寫成本專案安裝的 psycopg 3 驅動。
- **閒置時會休眠。** 約 15 分鐘沒有流量後，下一個請求要等 30-50 秒冷啟動。資料庫引擎設了
  `pool_pre_ping`，確保那個請求不會因為休眠期間被資料庫關掉的連線而失敗。

schema 變更由 `docker-entrypoint.sh` 套用：先跑 `alembic upgrade head`，成功才啟動 server。
migration 失敗會直接讓部署失敗，而不是讓 API 對著一個程式碼不認得的 schema 提供服務。
為什麼不用 Render 的 `preDeployCommand`，見 `alembic/README.md`。

`JWT_SECRET` 在 `render.yaml` 裡宣告成 `generateValue: true`，Render 會在第一次套用時產生
一組亂數並在後續部署沿用。這個 repo 裡從來不會出現任何密鑰，而且程式在偵測到「正式資料庫
搭配開發用預設密鑰」時會拒絕啟動。

---

### API

除了 `/health`、`/auth/register` 與 `/auth/login` 之外，每個路由都需要
`Authorization: Bearer <token>`。所有資料都會限縮在 token 所代表的那個帳號。

| 方法 | 路徑 | 說明 |
|---|---|---|
| `GET` | `/health` | 不需驗證的存活探測 |
| `GET` | `/auth/config` | 不需驗證；告訴登入畫面要不要顯示註冊入口 |
| `POST` | `/auth/register` `/auth/login` | 未開放 `ALLOW_REGISTRATION` 時註冊回 403。登入走 OAuth2 password flow（form 編碼），回傳 JWT |
| `GET` `POST` | `/auth/me` `/auth/password` | 目前帳號；修改密碼（會回傳新的 token） |
| `GET` `POST` | `/assets/snapshots` | 分頁列表（上限 200）；建立 |
| `GET` `PUT` `DELETE` | `/assets/snapshots/{id}` | |
| `GET` | `/assets/snapshots/{id}/categories` | SQL `GROUP BY` 加總 |
| `GET` `PUT` `DELETE` | `/assets/goal` | 存錢目標、用途、下一步 |
| `GET` `POST` | `/reminders` | 可用 `active_only`、`due_within_days` 過濾 |
| `GET` `POST` | `/todos` | 可用 `done`、`due_before` 過濾；`PUT /todos/order` 重新排序 |
| `PATCH` `DELETE` | `/todos/{id}` | `PATCH` 是部分更新 |
| `GET` `POST` | `/lists` | 自訂欄位；`PUT /lists/order` |
| `POST` `PUT` `DELETE` | `/lists/{id}/items` | 每列是符合該清單欄位定義的 JSON |
| `GET` `POST` | `/ideas` | |
| `GET` `POST` | `/grocery/meal-ideas` `/grocery/recipes` `/grocery/shopping` | |
| `GET` `PUT` `DELETE` | `/travel` | 行程本體；住宿、打包、權益、支出都掛在底下 |
| `POST` | `/travel/expenses/scan` | 收據 OCR；沒有 Tesseract 時降級為只上傳 |
| `GET` | `/travel/lodging-suggestions` | 從日曆事件解析住宿資訊 |
| `GET` `PATCH` | `/settings` | 每個帳號的 Telegram 與日曆設定 |
| `POST` | `/settings/telegram/test` | 發送測試訊息 |
| `GET` | `/today` | 本地資料與日曆來源合併 |
| `POST` | `/today/notify` | 把摘要推播到 Telegram |


### 設計決策

**金額用 `Numeric(14,2)`，不用 `float`。** 二進位浮點數無法精確表示 0.01，誤差會在加總
時累積。`total` 一路保持 `Decimal` 到 JSON，理由相同。

**密碼用 pwdlib 的 Argon2id。** passlib 從 2020 年起沒有再發布版本，而且對 bcrypt 4.1+
會壞掉；`PasswordHash.recommended()` 會選 Argon2id，並把這個選擇集中在一個地方。

**沒有 refresh token。** 多一種 token 型別，驗證的攻擊面大約會翻倍；對個人工具來說，
每天重新登入一次的成本，低於把 refresh token 輪替做得似是而非的成本。

**註冊預設關閉，而「預設值」本身就是那個安全性質。** 個人部署是放在公開網址上的，
端點開著就代表任何找到它的陌生人都能分走免費實例的資源和那 0.5 GB 資料庫。
預設開放、指望部署時去關掉，等於把失效模式弄反了——忘記設定時應該是「沒人能註冊」，
而不是「誰都能註冊」。這個檢查排在查詢帳號名之前，所以關閉的服務也不能被拿來探測
哪些帳號名已被使用。

**整合設定屬於各個帳號，而且日曆沒有全服務後備。** 在個人應用裡，後備機制會造成意外：
新建立的帳號在自己連上日曆之前，可能會看起來像是有別人的測試日曆。

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

**建置產物永久快取，`index.html` 完全不快取。** Vite 會把內容雜湊寫進每個資源檔名，
所以那些檔案不可能改變，可以標成 `immutable`。而 `index.html` 的任務就是指出目前用的是
哪些檔案，快取它正是瀏覽器跑到上週 JavaScript 的原因。

**Telegram 訊息做 HTML 跳脫。** `parse_mode=HTML` 加上一個叫 `<b>rent` 的待辦會讓訊息
壞掉。有測試。

---

### 取捨與限制

誠實說明這個專案不是什麼：

- **測試跑在 SQLite，正式環境是 Postgres。** CI 會對兩者都驗證 migration，但查詢路徑
  只在 SQLite 上被覆蓋。解法是加 Postgres matrix build，還在清單上。
- **Telegram bot token 以明文儲存。** 曝險程度跟 `DATABASE_URL` 相同：能讀資料庫的人就能
  讀到它，而這個 token 只能往一個聊天室發訊息。如果是替很多人保管 token 的服務，就該用
  一把資料庫本身沒有的金鑰加密。
- **收據圖片以 bytes 存在 Postgres 裡**，單張上限 8 MB。少量沒問題，量大就不對——
  0.5 GB 的免費方案資料庫大約只放得下六十張滿版收據。如果收據變成日常，解法是改用物件儲存。
- **日曆快取在行程記憶體內**，以來源網址為鍵，上限 64 筆。開多個 instance 各自持有一份，
  解法是 Redis。
- **用 iCal 而非 Google Calendar API。** 不需要 OAuth 流程、token 儲存或 Cloud 專案，
  代價是只能唯讀存取單一日曆。
- **Migration 在容器啟動時跑，不是 pre-deploy。** Render 的 `preDeployCommand` 才是正確
  位置，但那是付費方案功能。免費方案只有一個 instance，不會有競爭；一旦要擴充，這行就得搬家。
- **免費方案會冷啟動。** 休眠後第一個請求要等 30-50 秒。這是方案的限制而非程式的問題，
  但對真實使用者來說兩者沒有差別；付費方案或定時 ping 都能解決。

### 待辦

- [x] Alembic migrations
- [x] 多使用者帳號與驗證
- [x] 用這個 API 的網頁前端
- [ ] CI 加入 Postgres（matrix build），讓部署實際用到的查詢路徑也進測試
- [ ] 由提醒自動產生週期性待辦
- [ ] 收據圖片改存物件儲存，而不是塞在資料庫裡

### 授權

MIT
