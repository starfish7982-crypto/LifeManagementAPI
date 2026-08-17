import { useState } from "react";

import { Donut, TrendLine } from "../components/charts";
import { Field, Modal } from "../components/Modal";
import { ViewFrame } from "../components/ViewFrame";
import { api } from "../lib/api";
import { useToast } from "../lib/context";
import { fmtDate, money, monthLabel, todayISO } from "../lib/format";
import { t } from "../lib/i18n";
import { useResource } from "../lib/useResource";
import type { Goal } from "../lib/types";

const WINDOW_DAYS = 45;

export function Dashboard({ onOpenReminders }: { onOpenReminders: () => void }) {
  const snapshots = useResource(() => api.snapshots());
  const goal = useResource(() => api.goal());
  const reminders = useResource(() => api.reminders(true));
  const [editing, setEditing] = useState(false);

  const list = snapshots.data ?? [];
  const latest = list[0];
  const previous = list[1];

  return (
    <ViewFrame
      title={t("dashboard_title")}
      subtitle={
        latest
          ? t("dashboard_sub", { today: fmtDate(todayISO()), month: monthLabel(latest.month) })
          : ""
      }
      resources={[snapshots, goal, reminders]}
    >
      {!latest && <div className="empty-note">{t("no_snapshots")}</div>}

      {latest && (
        <>
          <div className="dashboard-grid">
            <NetWorthCard
              netWorth={Number(latest.total)}
              previousTotal={previous ? Number(previous.total) : null}
              previousMonth={previous ? monthLabel(previous.month) : ""}
              items={latest.items}
              goal={goal.data ?? null}
              onEditGoal={() => setEditing(true)}
            />

            <div className="card dashboard-reminders-card">
              <h2>{t("upcoming_reminders", { days: WINDOW_DAYS })}</h2>
              {(() => {
                const upcoming = (reminders.data ?? [])
                  .filter((r) => r.days_until_due !== null && r.days_until_due <= WINDOW_DAYS)
                  .slice(0, 8);
                if (upcoming.length === 0)
                  return <div className="empty-note">{t("no_upcoming")}</div>;
                return upcoming.map((r) => (
                  <div className="due-item" key={r.id}>
                    <span className="badge">
                      {r.days_until_due === 0
                        ? t("due_today")
                        : t("due_in_days", { n: r.days_until_due ?? 0 })}
                    </span>
                    <div className="t">{r.title}</div>
                    <span className="d">{fmtDate(r.next_due)}</span>
                  </div>
                ));
              })()}
              <button
                type="button"
                className="btn ghost manage-reminders"
                onClick={onOpenReminders}
              >
                {t("manage_reminders")}
              </button>
            </div>
          </div>

          <div className="card dashboard-trend-card">
            <h2>{t("monthly_trend")}</h2>
            {/* The API returns newest first; a time series has to read the other way. */}
            <TrendLine
              points={[...list]
                .reverse()
                .map((s) => ({ label: monthLabel(s.month), value: Number(s.total) }))}
            />
          </div>
        </>
      )}

      {editing && (
        <GoalModal
          goal={goal.data ?? null}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            goal.reload();
          }}
        />
      )}
    </ViewFrame>
  );
}

function NetWorthCard({
  netWorth,
  previousTotal,
  previousMonth,
  items,
  goal,
  onEditGoal,
}: {
  netWorth: number;
  previousTotal: number | null;
  previousMonth: string;
  items: { category: string; amount: string }[];
  goal: Goal | null;
  onEditGoal: () => void;
}) {
  const byCategory = new Map<string, number>();
  for (const item of items) {
    byCategory.set(item.category, (byCategory.get(item.category) ?? 0) + Number(item.amount));
  }
  const slices = [...byCategory]
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value);

  const delta = previousTotal === null ? null : netWorth - previousTotal;
  const pct = previousTotal ? ((delta ?? 0) / previousTotal) * 100 : null;

  // The goal tracks one category when its purpose names one, else total net worth.
  const current = goal ? (byCategory.get(goal.category ?? goal.purpose) ?? netWorth) : 0;
  const progress = goal ? Math.min(100, (current / Number(goal.amount)) * 100) : 0;

  return (
    <div className="card dashboard-net-worth-card">
      <div className="card-head-row">
        <h2>{t("net_worth")}</h2>
        <div className="goal-mini">
          <div className="goal-mini-title">
            {t("short_term_goal")}
            {goal ? ` · ${goal.category ?? goal.purpose}` : ""}
          </div>
          {goal && (
            <button
              type="button"
              className="goal-summary"
              aria-label={t("edit")}
              onClick={onEditGoal}
            >
              <span>{Number(goal.amount).toLocaleString()}</span>
              <span>{goal.purpose}</span>
              {goal.next_step && <span className="goal-next-step">{goal.next_step}</span>}
            </button>
          )}
          {!goal && (
            <button type="button" className="btn subtle" onClick={onEditGoal}>
              {t("add")}
            </button>
          )}
          {goal && (
            <>
              <div className="goal-progress">
                <div className="goal-bar">
                  <div className="goal-fill" style={{ width: `${progress}%` }} />
                </div>
                <div className="goal-stats">
                  {t("goal_progress", {
                    current: money(current),
                    pct: progress.toFixed(1),
                    gap: money(Math.max(0, Number(goal.amount) - current)),
                  })}
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="hero-num">{money(netWorth, 2)}</div>

      {delta !== null && (
        <div className={`delta ${delta >= 0 ? "up" : "down"}`}>
          {delta >= 0 ? "▲" : "▼"} {money(Math.abs(delta))}
          {pct !== null && ` (${Math.abs(pct).toFixed(1)}%)`}{" "}
          <span className="delta-note">{t("vs_previous", { month: previousMonth })}</span>
        </div>
      )}

      <Donut slices={slices} centreValue={money(netWorth, 2)} centreLabel={t("net_worth")} />
    </div>
  );
}

function GoalModal({
  goal,
  onClose,
  onSaved,
}: {
  goal: Goal | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  return (
    <Modal
      title={t("short_term_goal")}
      onClose={onClose}
      busy={busy}
      onSubmit={async (form) => {
        setBusy(true);
        try {
          await api.setGoal({
            // Kept as the input's string all the way to the server: routing it through
            // a JS number would undo the reason the column is Numeric(14, 2).
            amount: String(form.get("amount") ?? ""),
            category: String(form.get("category") ?? "") || null,
            purpose: String(form.get("purpose") ?? ""),
            next_step: String(form.get("next_step") ?? "") || null,
          });
          toast(t("saved"));
          onSaved();
        } finally {
          setBusy(false);
        }
      }}
    >
      <Field label={t("goal_amount")}>
        <input
          name="amount"
          type="number"
          step="0.01"
          min="0.01"
          required
          defaultValue={goal?.amount ?? ""}
        />
      </Field>
      <Field label={t("goal_category")}>
        <input name="category" required maxLength={60} defaultValue={goal?.category ?? goal?.purpose ?? ""} />
      </Field>
      <Field label={t("goal_purpose")}>
        <input name="purpose" required maxLength={200} defaultValue={goal?.purpose ?? ""} />
      </Field>
      <Field label={t("goal_next")}>
        <input name="next_step" maxLength={200} defaultValue={goal?.next_step ?? ""} />
      </Field>
    </Modal>
  );
}
