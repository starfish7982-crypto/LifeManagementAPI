import { locale } from "./i18n";

/**
 * Formatting helpers.
 *
 * There is no `esc()` here, and its absence is the point. The previous implementation
 * built markup as strings, so every interpolated value had to be escaped by hand and a
 * single missed one was an injection bug. JSX escapes by default: `{value}` is text,
 * never markup, unless someone explicitly reaches for dangerouslySetInnerHTML. A whole
 * category of mistake stops being possible rather than being handled carefully.
 */

/** Money arrives from the API as a decimal string; `Number` is used only to format. */
export function money(value: string | number, decimals = 0): string {
  return Number(value ?? 0).toLocaleString(locale(), {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Compact form for chart axes: $84k rather than $84,000. */
export function moneyShort(value: number): string {
  if (Math.abs(value) >= 1000) return `$${Math.round(value / 1000)}k`;
  return `$${Math.round(value)}`;
}

export const todayISO = (): string => new Date().toISOString().slice(0, 10);

export function fmtDate(iso: string | null): string {
  if (!iso) return "";
  return iso.slice(0, 10).replace(/-/g, "/");
}

export function monthLabel(iso: string): string {
  const [y, m] = iso.slice(0, 7).split("-");
  if (!y || !m) return "";
  return new Date(Number(y), Number(m) - 1, 1).toLocaleDateString(locale(), {
    year: "numeric",
    month: "long",
  });
}

export function longDate(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(locale(), {
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "short",
  });
}

const PALETTE = ["#2a78d6", "#1baf7a", "#eda100", "#008300", "#4a3aa7", "#d03b3b", "#898781"];
export const colourFor = (i: number): string => PALETTE[i % PALETTE.length] ?? "#898781";
