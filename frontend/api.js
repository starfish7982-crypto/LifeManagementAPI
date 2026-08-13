/**
 * The REST client, and the session it carries.
 *
 * This replaces the old `apiLoad`/`apiSave` pair, which read and wrote whole JSON files
 * through a single `/api/file` endpoint. Every caller there held an entire document in
 * memory and posted the whole thing back on any edit — last writer wins, and a failed
 * save silently discarded the change. Here each call names one resource.
 *
 * The token lives in localStorage. That is a real trade-off: script running on this
 * origin can read it, so an XSS bug becomes a stolen session. The alternative is an
 * HttpOnly cookie, which JavaScript cannot touch — but cookies are attached by the
 * browser automatically, which is what CSRF exploits, so that route trades one class
 * of bug for another and needs its own defence. For a single-user app with no
 * third-party scripts on the page, localStorage is the smaller surface. The mitigation
 * that matters either way is not injecting untrusted HTML, which is why `esc()` in
 * ui.js is used on every value that reaches the DOM.
 */

const TOKEN_KEY = "lm.token";
const EMAIL_KEY = "lm.email";

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

export const session = {
  get token() {
    return localStorage.getItem(TOKEN_KEY);
  },
  get email() {
    return localStorage.getItem(EMAIL_KEY);
  },
  save(token, email) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(EMAIL_KEY, email);
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(EMAIL_KEY);
  },
};

/** Called when the server rejects our token, so the shell can show the sign-in screen. */
let onUnauthorised = () => {};
export function setUnauthorisedHandler(fn) {
  onUnauthorised = fn;
}

/**
 * Pull the human-readable part out of an error body.
 *
 * FastAPI answers with `detail`, which is a string for HTTPException and an array of
 * per-field objects for validation failures. Rendering the array raw puts
 * "[object Object]" in front of the user.
 */
function describe(status, body) {
  const detail = body?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const field = (d.loc || []).filter((p) => p !== "body").join(".");
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  return `請求失敗 (${status})`;
}

async function request(method, path, { body, auth = true } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth && session.token) headers.Authorization = `Bearer ${session.token}`;

  let response;
  try {
    // Absolute from the site root. The API is served from the same origin as this page
    // (see `app/main.py`), which is why there is no base URL to configure and no CORS
    // preflight on any of these calls.
    response = await fetch(path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    // fetch only rejects when the request never got an answer at all.
    throw new ApiError(0, "連線失敗，請檢查網路後重試");
  }

  if (response.status === 401 && auth) {
    // The token is expired or the account is gone. Drop it and get out of the way;
    // leaving it in place would make every subsequent view fail the same way.
    session.clear();
    onUnauthorised();
    throw new ApiError(401, "登入已過期，請重新登入");
  }

  if (response.status === 204) return null;

  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;

  if (!response.ok) throw new ApiError(response.status, describe(response.status, payload));
  return payload;
}

const get = (p) => request("GET", p);
const post = (p, body) => request("POST", p, { body });
const put = (p, body) => request("PUT", p, { body });
const patch = (p, body) => request("PATCH", p, { body });
const del = (p) => request("DELETE", p);

export const api = {
  // ---------------------------------------------------------------------- auth
  async register(email, password) {
    return request("POST", "/auth/register", { body: { email, password }, auth: false });
  },

  async login(email, password) {
    // The OAuth2 password flow is form-encoded, not JSON, and names the field
    // `username` — so this one endpoint does not go through `request()`.
    const body = new URLSearchParams({ username: email, password });
    let response;
    try {
      response = await fetch("/auth/login", { method: "POST", body });
    } catch {
      throw new ApiError(0, "連線失敗，請檢查網路後重試");
    }
    const text = await response.text();
    const payload = text ? JSON.parse(text) : null;
    if (!response.ok) throw new ApiError(response.status, describe(response.status, payload));
    session.save(payload.access_token, email);
    return payload;
  },

  me: () => get("/auth/me"),

  async changePassword(currentPassword, newPassword) {
    const payload = await post("/auth/password", {
      current_password: currentPassword,
      new_password: newPassword,
    });
    // The server issues a fresh token; storing it keeps the session alive rather than
    // bouncing the user to the sign-in screen right after they proved who they are.
    session.save(payload.access_token, session.email);
    return payload;
  },

  // -------------------------------------------------------------------- today
  today: (day) => get(day ? `/today?day=${day}` : "/today"),

  // -------------------------------------------------------------------- todos
  todos: () => get("/todos"),
  createTodo: (todo) => post("/todos", todo),
  patchTodo: (id, changes) => patch(`/todos/${id}`, changes),
  deleteTodo: (id) => del(`/todos/${id}`),

  // ----------------------------------------------------------------- reminders
  reminders: (activeOnly = false) => get(`/reminders?active_only=${activeOnly}`),
  createReminder: (r) => post("/reminders", r),
  replaceReminder: (id, r) => put(`/reminders/${id}`, r),
  deleteReminder: (id) => del(`/reminders/${id}`),

  // -------------------------------------------------------------------- assets
  snapshots: () => get("/assets/snapshots"),
  snapshot: (id) => get(`/assets/snapshots/${id}`),
  createSnapshot: (s) => post("/assets/snapshots", s),
  replaceSnapshot: (id, s) => put(`/assets/snapshots/${id}`, s),
  deleteSnapshot: (id) => del(`/assets/snapshots/${id}`),
  categories: () => get("/assets/categories"),
  goal: () => get("/assets/goal"),
  setGoal: (g) => put("/assets/goal", g),

  // --------------------------------------------------------------------- lists
  lists: () => get("/lists"),
  createList: (l) => post("/lists", l),
  replaceList: (id, l) => put(`/lists/${id}`, l),
  deleteList: (id) => del(`/lists/${id}`),
  createRow: (listId, values) => post(`/lists/${listId}/items`, { values }),
  replaceRow: (listId, rowId, values) => put(`/lists/${listId}/items/${rowId}`, { values }),
  deleteRow: (listId, rowId) => del(`/lists/${listId}/items/${rowId}`),
};
