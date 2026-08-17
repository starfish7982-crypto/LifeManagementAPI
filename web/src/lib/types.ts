/**
 * The API's contract, in TypeScript.
 *
 * Hand-written rather than generated from openapi.json. Generation would guarantee
 * they never drift, and for a larger API that is the right call; at this size the
 * generated output is harder to read than the schemas it came from, and the drift it
 * prevents is caught by `npm run typecheck` against a running server anyway. The one
 * rule that makes this safe is that nothing here is invented: every field below exists
 * in `app/schemas.py`, spelled the same way.
 *
 * Money is `string`, everywhere, deliberately. The API sends decimal strings because
 * the columns are Numeric(14, 2), and parsing them into JS numbers on arrival would
 * reintroduce exactly the floating-point error the column type exists to avoid. They
 * are parsed only where arithmetic is unavoidable — chart maths — and never on the way
 * back to the server.
 */

export interface User {
  id: number;
  username: string;
  created_at: string;
}

export interface Token {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export type Frequency = "once" | "monthly" | "yearly";

export interface Reminder {
  id: number;
  title: string;
  frequency: Frequency;
  day_of_month: number | null;
  month_of_year: number | null;
  on_date: string | null;
  active: boolean;
  days_before: number;
  note: string | null;
  created_at: string;
  next_due: string | null;
  days_until_due: number | null;
}

/** The write shape. The fields that do not apply to the chosen frequency are absent
 *  rather than null, because the API's cross-field validation rejects the latter. */
export interface ReminderIn {
  title: string;
  frequency: Frequency;
  active: boolean;
  days_before: number;
  note: string | null;
  day_of_month?: number;
  month_of_year?: number;
  on_date?: string;
}

export interface Todo {
  id: number;
  title: string;
  due_date: string | null;
  done: boolean;
  bucket: "today" | "later";
  position: number;
  source: string;
  calendar_time: string | null;
  created_at: string;
}

export interface AssetItem {
  id: number;
  name: string;
  category: string;
  amount: string;
  currency: string;
}

export interface AssetItemIn {
  name: string;
  category: string;
  amount: string;
  currency?: string;
}

export interface Snapshot {
  id: number;
  month: string;
  note: string | null;
  created_at: string;
  items: AssetItem[];
  total: string;
}

export interface SnapshotIn {
  month: string;
  note: string | null;
  items: AssetItemIn[];
}

export interface Goal {
  amount: string;
  category: string | null;
  purpose: string;
  next_step: string | null;
  updated_at: string;
}

export interface GoalIn {
  amount: string;
  category: string | null;
  purpose: string;
  next_step: string | null;
}

export interface ListRow {
  id: number;
  values: string[];
  position: number;
}

export interface ListTable {
  id: number;
  name: string;
  icon: string | null;
  columns: string[];
  position: number;
  created_at: string;
  items: ListRow[];
}

export interface ListIn {
  name: string;
  icon: string | null;
  columns: string[];
  position: number;
}

export interface CalendarEvent {
  title: string;
  starts_at: string;
  starts_time: string | null;
  all_day: boolean;
}

export interface TodayPayload {
  date: string;
  todos: Todo[];
  reminders_due: Reminder[];
  calendar_events: CalendarEvent[];
}

/* ------------------------------------------------------------------------ ideas */

export interface Idea {
  id: number;
  text: string;
  note: string | null;
  created_at: string;
}

/* ---------------------------------------------------------------------- grocery */

export interface ShoppingItem {
  id: number;
  text: string;
  quantity: string | null;
  done: boolean;
  position: number;
}

export interface Recipe {
  id: number;
  name: string;
  ingredients: string | null;
  steps: string | null;
  temp: string | null;
  video_url: string | null;
  created_at: string;
}

export type RecipeIn = Omit<Recipe, "id" | "created_at">;

export interface MealIdea {
  id: number;
  category: string;
  name: string;
  status: string;
}

export type MealIdeaIn = Omit<MealIdea, "id">;

/* ----------------------------------------------------------------------- travel */

export interface Lodging {
  id: number;
  name: string;
  check_in: string | null;
  check_out: string | null;
  address: string | null;
  confirmation_number: string | null;
  phone: string | null;
  details: string | null;
}

export interface CalendarLodgingSuggestion {
  name: string;
  check_in: string | null;
  check_out: string | null;
  address: string | null;
  confirmation_number: string | null;
  phone: string | null;
  details: string | null;
}

export interface PackingItem {
  id: number;
  text: string;
  done: boolean;
  position: number;
}

export interface TravelBenefit {
  id: number;
  card_name: string;
  benefit: string | null;
  expires_at: string | null;
}

export type TravelBenefitIn = Omit<TravelBenefit, "id">;

export interface TravelExpense {
  id: number;
  merchant: string;
  amount: string;
  spent_at: string;
  category: string | null;
  note: string | null;
  has_receipt: boolean;
  receipt_filename: string | null;
  ocr_text: string | null;
}

export type TravelExpenseIn = Pick<TravelExpense, "merchant" | "amount" | "spent_at" | "category" | "note">;

export interface Trip {
  start_date: string | null;
  end_date: string | null;
  license_plate: string | null;
  updated_at: string;
  lodgings: Lodging[];
  packing: PackingItem[];
  expenses: TravelExpense[];
}

/* --------------------------------------------------------------------- settings */

/** Note what is absent: the bot token. The API never returns it — a secret that has
 *  been written should not be readable back — so there is no field here to hold it. */
export interface UserSettings {
  telegram_configured: boolean;
  telegram_chat_id: string | null;
  google_calendar_ical_url: string | null;
  updated_at: string | null;
}

export interface UserSettingsPatch {
  telegram_bot_token?: string;
  telegram_chat_id?: string;
  google_calendar_ical_url?: string;
}
