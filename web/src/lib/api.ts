/**
 * The REST client and the session it carries.
 *
 * The token lives in localStorage. That is a real trade-off: script running on this
 * origin can read it, so an XSS bug becomes a stolen session. The alternative is an
 * HttpOnly cookie, which JavaScript cannot touch — but cookies are attached by the
 * browser automatically, which is what CSRF exploits, so that route swaps one class of
 * bug for another and needs its own defence. For a single-user app with no third-party
 * scripts, localStorage is the smaller surface. React helps on the other side of the
 * trade: JSX escapes interpolated values by default, so the injection path that would
 * make the token reachable is closed unless someone reaches for dangerouslySetInnerHTML.
 */

import { t } from "./i18n";
import type {
  AuthConfig,
  Goal,
  GoalIn,
  Idea,
  ListIn,
  ListTable,
  Recipe,
  RecipeIn,
  MealIdea,
  MealIdeaIn,
  Reminder,
  ReminderIn,
  ShoppingItem,
  Snapshot,
  SnapshotIn,
  Todo,
  TodayPayload,
  Token,
  Trip,
  Lodging,
  CalendarLodgingSuggestion,
  PackingItem,
  PackingList,
  TravelBenefit,
  TravelBenefitIn,
  TravelExpense,
  TravelExpenseIn,
  User,
  UserSettings,
  UserSettingsPatch,
} from "./types";

const TOKEN_KEY = "lm.token";
const USERNAME_KEY = "lm.username";
const LEGACY_EMAIL_KEY = "lm.email";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export const session = {
  get token(): string | null {
    return localStorage.getItem(TOKEN_KEY);
  },
  get username(): string | null {
    // Existing signed-in browsers retain their name until /auth/me refreshes it.
    return localStorage.getItem(USERNAME_KEY) ?? localStorage.getItem(LEGACY_EMAIL_KEY);
  },
  save(token: string, username: string): void {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USERNAME_KEY, username);
    localStorage.removeItem(LEGACY_EMAIL_KEY);
  },
  clear(): void {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USERNAME_KEY);
    localStorage.removeItem(LEGACY_EMAIL_KEY);
  },
};

/** Called when the server rejects our token, so the shell can show the sign-in screen. */
let onUnauthorised: () => void = () => {};
export function setUnauthorisedHandler(fn: () => void): void {
  onUnauthorised = fn;
}

interface ValidationItem {
  loc: (string | number)[];
  msg: string;
}

/**
 * Pull the human-readable part out of an error body.
 *
 * FastAPI answers with `detail`: a string for HTTPException, an array of per-field
 * objects for validation failures. Rendering the array raw puts "[object Object]" in
 * front of the user.
 */
function describe(status: number, body: unknown): string {
  if (status >= 500) {
    // The server does not send its traceback to the browser, and should not. Point at
    // where the traceback actually is instead of relaying a message with nothing in it.
    return t("server_error", { status });
  }
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return (detail as ValidationItem[])
      .map((d) => {
        const field = (d.loc ?? []).filter((p) => p !== "body").join(".");
        return field ? `${field}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  return t("request_failed", { status });
}

/**
 * Parse the body, tolerating one that is not JSON.
 *
 * An unhandled exception does not come back as JSON — the server answers with the
 * plain string "Internal Server Error". Calling JSON.parse on that throws
 * `Unexpected token 'I'`, which replaces a real 500 with a parse error and sends
 * whoever is debugging it looking in the wrong place. Proxies do the same with HTML.
 */
async function readBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { detail: text.slice(0, 300) };
  }
}

interface RequestOptions {
  body?: unknown;
  auth?: boolean;
}

async function request<T>(
  method: string,
  path: string,
  { body, auth = true }: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = session.token;
  if (auth && token) headers["Authorization"] = `Bearer ${token}`;

  // `body` is omitted rather than set to undefined. Under exactOptionalPropertyTypes
  // those are different things: RequestInit declares `body?: BodyInit | null`, which
  // permits the property to be absent but not to be present-and-undefined. The
  // distinction is pedantic here and load-bearing elsewhere — it is what stops
  // `{ note: undefined }` from being sent as a field the API reads as null.
  const init: RequestInit = { method, headers };
  if (body !== undefined) init.body = JSON.stringify(body);

  let response: Response;
  try {
    // Absolute from the site root. The API is served from the same origin as this page
    // in production, and Vite proxies these paths in development, so there is no base
    // URL to configure and no CORS preflight on any call.
    response = await fetch(path, init);
  } catch {
    // fetch only rejects when the request never got an answer at all.
    throw new ApiError(0, t("network_error"));
  }

  if (response.status === 401 && auth) {
    // The token is expired or the account is gone. Drop it and get out of the way;
    // leaving it in place would make every subsequent view fail the same way.
    session.clear();
    onUnauthorised();
    throw new ApiError(401, t("session_expired"));
  }

  if (response.status === 204) return null as T;

  const payload = await readBody(response);
  if (!response.ok) throw new ApiError(response.status, describe(response.status, payload));
  return payload as T;
}

const get = <T,>(p: string) => request<T>("GET", p);
const post = <T,>(p: string, body?: unknown) => request<T>("POST", p, { body });
const put = <T,>(p: string, body: unknown) => request<T>("PUT", p, { body });
const patch = <T,>(p: string, body: unknown) => request<T>("PATCH", p, { body });
const del = (p: string) => request<null>("DELETE", p);

async function upload<T>(path: string, field: string, file: File): Promise<T> {
  const headers: Record<string, string> = {};
  const token = session.token;
  if (token) headers["Authorization"] = `Bearer ${token}`;
  const body = new FormData();
  body.append(field, file);
  let response: Response;
  try {
    response = await fetch(path, { method: "POST", headers, body });
  } catch {
    throw new ApiError(0, t("network_error"));
  }
  if (response.status === 401) {
    session.clear();
    onUnauthorised();
    throw new ApiError(401, t("session_expired"));
  }
  const payload = await readBody(response);
  if (!response.ok) throw new ApiError(response.status, describe(response.status, payload));
  return payload as T;
}

export const api = {
  // ------------------------------------------------------------------------ auth
  authConfig: () => request<AuthConfig>("GET", "/auth/config", { auth: false }),

  register: (username: string, password: string) =>
    request<User>("POST", "/auth/register", { body: { username, password }, auth: false }),

  async login(username: string, password: string): Promise<Token> {
    // The OAuth2 password flow is form-encoded, not JSON, and names the field
    // `username` — so this one endpoint does not go through `request()`.
    const body = new URLSearchParams({ username, password });
    let response: Response;
    try {
      response = await fetch("/auth/login", { method: "POST", body });
    } catch {
      throw new ApiError(0, t("network_error"));
    }
    const payload = await readBody(response);
    if (!response.ok) throw new ApiError(response.status, describe(response.status, payload));
    const token = payload as Token;
    session.save(token.access_token, username);
    return token;
  },

  async changePassword(currentPassword: string, newPassword: string): Promise<Token> {
    const token = await post<Token>("/auth/password", {
      current_password: currentPassword,
      new_password: newPassword,
    });
    // The server issues a fresh token; storing it keeps the session alive rather than
    // bouncing the user to the sign-in screen right after they proved who they are.
    session.save(token.access_token, session.username ?? "");
    return token;
  },

  me: () => get<User>("/auth/me"),

  // ----------------------------------------------------------------------- today
  today: (refreshCalendar = false) =>
    get<TodayPayload>(`/today${refreshCalendar ? "?refresh_calendar=true" : ""}`),

  // ----------------------------------------------------------------------- todos
  todos: () => get<Todo[]>("/todos"),
  createTodo: (todo: { title: string; due_date: string | null }) => post<Todo>("/todos", todo),
  patchTodo: (id: number, changes: Partial<Pick<Todo, "title" | "due_date" | "done" | "bucket">>) =>
    patch<Todo>(`/todos/${id}`, changes),
  deleteTodo: (id: number) => del(`/todos/${id}`),
  reorderTodos: (bucket: Todo["bucket"], ids: number[]) =>
    put<Todo[]>("/todos/order", { bucket, ids }),

  // ------------------------------------------------------------------- reminders
  reminders: (activeOnly = false) => get<Reminder[]>(`/reminders?active_only=${activeOnly}`),
  createReminder: (r: ReminderIn) => post<Reminder>("/reminders", r),
  replaceReminder: (id: number, r: ReminderIn) => put<Reminder>(`/reminders/${id}`, r),
  deleteReminder: (id: number) => del(`/reminders/${id}`),

  // ---------------------------------------------------------------------- assets
  snapshots: () => get<Snapshot[]>("/assets/snapshots"),
  snapshot: (id: number) => get<Snapshot>(`/assets/snapshots/${id}`),
  createSnapshot: (s: SnapshotIn) => post<Snapshot>("/assets/snapshots", s),
  replaceSnapshot: (id: number, s: SnapshotIn) => put<Snapshot>(`/assets/snapshots/${id}`, s),
  deleteSnapshot: (id: number) => del(`/assets/snapshots/${id}`),
  categories: () => get<string[]>("/assets/categories"),
  goal: () => get<Goal | null>("/assets/goal"),
  setGoal: (g: GoalIn) => put<Goal>("/assets/goal", g),

  // ----------------------------------------------------------------------- lists
  lists: () => get<ListTable[]>("/lists"),
  createList: (l: ListIn) => post<ListTable>("/lists", l),
  replaceList: (id: number, l: ListIn) => put<ListTable>(`/lists/${id}`, l),
  deleteList: (id: number) => del(`/lists/${id}`),
  createRow: (listId: number, values: string[]) =>
    post<ListRowResponse>(`/lists/${listId}/items`, { values }),
  replaceRow: (listId: number, rowId: number, values: string[]) =>
    put<ListRowResponse>(`/lists/${listId}/items/${rowId}`, { values }),
  deleteRow: (listId: number, rowId: number) => del(`/lists/${listId}/items/${rowId}`),
  reorderRows: (listId: number, ids: number[]) =>
    put<ListTable>(`/lists/${listId}/items/order`, { ids }),
  reorderLists: (ids: number[]) => put<ListTable[]>("/lists/order", { ids }),

  // ----------------------------------------------------------------------- ideas
  ideas: () => get<Idea[]>("/ideas"),
  createIdea: (i: { text: string; note: string | null }) => post<Idea>("/ideas", i),
  replaceIdea: (id: number, i: { text: string; note: string | null }) =>
    put<Idea>(`/ideas/${id}`, i),
  deleteIdea: (id: number) => del(`/ideas/${id}`),

  // --------------------------------------------------------------------- grocery
  shopping: () => get<ShoppingItem[]>("/grocery/shopping"),
  addShopping: (i: { text: string; quantity: string | null }) =>
    post<ShoppingItem>("/grocery/shopping", i),
  patchShopping: (id: number, changes: Partial<Pick<ShoppingItem, "text" | "quantity" | "done">>) =>
    patch<ShoppingItem>(`/grocery/shopping/${id}`, changes),
  deleteShopping: (id: number) => del(`/grocery/shopping/${id}`),
  clearShopping: (doneOnly: boolean) => del(`/grocery/shopping?done_only=${doneOnly}`),

  recipes: () => get<Recipe[]>("/grocery/recipes"),
  createRecipe: (r: RecipeIn) => post<Recipe>("/grocery/recipes", r),
  replaceRecipe: (id: number, r: RecipeIn) => put<Recipe>(`/grocery/recipes/${id}`, r),
  deleteRecipe: (id: number) => del(`/grocery/recipes/${id}`),
  mealIdeas: () => get<MealIdea[]>("/grocery/meal-ideas"),
  createMealIdea: (idea: MealIdeaIn) => post<MealIdea>("/grocery/meal-ideas", idea),
  replaceMealIdea: (id: number, idea: MealIdeaIn) =>
    put<MealIdea>(`/grocery/meal-ideas/${id}`, idea),
  deleteMealIdea: (id: number) => del(`/grocery/meal-ideas/${id}`),

  // ---------------------------------------------------------------------- travel
  trip: () => get<Trip | null>("/travel"),
  setTrip: (t: { start_date: string | null; end_date: string | null; license_plate: string | null }) =>
    put<Trip>("/travel", t),
  clearTrip: () => del("/travel"),
  addLodging: (l: { name: string; check_in: string | null; check_out: string | null; address: string | null; confirmation_number: string | null; phone: string | null; details: string | null }) =>
    post<Lodging>("/travel/lodgings", l),
  lodgingSuggestions: (checkIn: string, checkOut: string) =>
    get<CalendarLodgingSuggestion[]>(`/travel/lodging-suggestions?check_in=${encodeURIComponent(checkIn)}&check_out=${encodeURIComponent(checkOut)}`),
  deleteLodging: (id: number) => del(`/travel/lodgings/${id}`),
  packingLists: () => get<PackingList[]>("/travel/packing-lists"),
  createPackingList: (name: string) => post<PackingList>("/travel/packing-lists", { name }),
  replacePackingList: (id: number, name: string) => put<PackingList>(`/travel/packing-lists/${id}`, { name }),
  deletePackingList: (id: number) => del(`/travel/packing-lists/${id}`),
  reorderPacking: (packingListId: number, ids: number[]) =>
    put<PackingItem[]>(`/travel/packing-lists/${packingListId}/items/order`, { ids }),
  addPacking: (text: string, packingListId?: number) =>
    post<PackingItem>(
      `/travel/packing${packingListId === undefined ? "" : `?packing_list_id=${packingListId}`}`,
      { text },
    ),
  togglePacking: (id: number, done: boolean) =>
    patch<PackingItem>(`/travel/packing/${id}?done=${done}`, {}),
  deletePacking: (id: number) => del(`/travel/packing/${id}`),
  createTravelExpense: (expense: TravelExpenseIn) => post<TravelExpense>("/travel/expenses", expense),
  scanTravelReceipt: (file: File) => upload<TravelExpense>("/travel/expenses/scan", "receipt", file),
  replaceTravelExpense: (id: number, expense: TravelExpenseIn) =>
    put<TravelExpense>(`/travel/expenses/${id}`, expense),
  deleteTravelExpense: (id: number) => del(`/travel/expenses/${id}`),
  travelBenefits: () => get<TravelBenefit[]>("/travel/benefits"),
  createTravelBenefit: (benefit: TravelBenefitIn) =>
    post<TravelBenefit>("/travel/benefits", benefit),
  replaceTravelBenefit: (id: number, benefit: TravelBenefitIn) =>
    put<TravelBenefit>(`/travel/benefits/${id}`, benefit),
  deleteTravelBenefit: (id: number) => del(`/travel/benefits/${id}`),

  // -------------------------------------------------------------------- settings
  settings: () => get<UserSettings>("/settings"),
  updateSettings: (s: UserSettingsPatch) => patch<UserSettings>("/settings", s),
  testTelegram: () => post<{ detail: string }>("/settings/telegram/test"),
  disconnectTelegram: () => del("/settings/telegram"),
};

type ListRowResponse = { id: number; values: string[]; position: number };
