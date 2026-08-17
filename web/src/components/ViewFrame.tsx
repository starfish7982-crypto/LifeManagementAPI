import type { ReactNode } from "react";

import { t } from "../lib/i18n";
import type { ResourceStatus } from "../lib/useResource";

/**
 * The header, loading state and error state every screen shares.
 *
 * Each view used to open with the same handful of lines checking `loading` and `error`
 * before it could say anything about its own subject. Collecting that here means a
 * view starts at the part that is actually specific to it, and — more usefully — that
 * no view can forget to render the error, which is how a failed fetch turns into a
 * blank screen with nothing to explain it.
 */
export function ViewFrame({
  title,
  subtitle,
  resources,
  children,
}: {
  title: string;
  subtitle?: string;
  resources: ResourceStatus[];
  children: ReactNode;
}) {
  const loading = resources.some((r) => r.loading);
  const refreshing = resources.some((r) => r.refreshing);
  const failed = resources.find((r) => r.error);

  return (
    <>
      <div className="card-head-row">
        <h1 className="page-title">{title}</h1>
        {/* A quiet marker rather than a spinner over the content. The screen stays
            usable and stays put; this only says that what you are looking at is a
            moment old. */}
        {refreshing && (
          <span className="refreshing" role="status">
            {t("refreshing")}
          </span>
        )}
      </div>
      {subtitle && <div className="page-sub">{subtitle}</div>}

      {failed?.error && (
        <div className="error-note">
          {failed.error.detail}{" "}
          <button className="btn small" onClick={() => resources.forEach((r) => r.reload())}>
            {t("retry")}
          </button>
        </div>
      )}

      {/* Only before the first response. The message names the cold start on purpose:
          a spinner with no explanation reads as a hang when the wait is most of a
          minute. Afterwards the previous data stays on screen while a refetch runs —
          replacing it would blank the page on every checkbox tick. */}
      {loading && !failed && <div className="loading">{t("loading")}</div>}

      {!loading && !failed && children}
    </>
  );
}
