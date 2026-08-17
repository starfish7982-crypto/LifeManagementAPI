import { useState } from "react";

import { Field, Modal } from "../components/Modal";
import { ViewFrame } from "../components/ViewFrame";
import { api } from "../lib/api";
import { useToast } from "../lib/context";
import { fmtDate, todayISO } from "../lib/format";
import { t } from "../lib/i18n";
import { useResource } from "../lib/useResource";
import type { Frequency, Reminder, ReminderIn } from "../lib/types";

export function Reminders() {
  const toast = useToast();
  const reminders = useResource(() => api.reminders(false));
  const [editing, setEditing] = useState<Reminder | null | "new">(null);

  const label: Record<Frequency, string> = {
    once: t("freq_once"),
    monthly: t("freq_monthly"),
    yearly: t("freq_yearly"),
  };

  const list = reminders.data ?? [];

  return (
    <ViewFrame
      title={t("reminders_title")}
      subtitle={t("reminders_sub", { n: list.length })}
      resources={[reminders]}
    >
      <div className="card">
        <button className="btn reminders-add" onClick={() => setEditing("new")}>
          {t("new_reminder")}
        </button>

        {list.length === 0 && <div className="empty-note">{t("no_reminders")}</div>}

        {list.length > 0 && (
          <div className="reminders-table">
            <div className="reminders-table-head">
              <span>{t("reminder_status")}</span><span>{t("reminder")}</span><span>{t("freq")}</span>
              <span>{t("next_date")}</span><span>{t("advance_notice")}</span><span aria-hidden="true" />
            </div>
            {list.map((r) => (
              <div
                className={`reminder-row ${r.active ? "" : "inactive"}`}
                key={r.id}
                role="button"
                tabIndex={0}
                onClick={() => setEditing(r)}
                onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") setEditing(r); }}
              >
                <span className={`badge ${reminderStatusClass(r)}`}>{reminderStatus(r)}</span>
                <div className="reminder-main">
                  <div className="todo-title">{r.title}</div>
                  {r.note && <div className="todo-note">{r.note}</div>}
                </div>
                <span className="freq-tag">{frequencyDescription(r, label)}</span>
                <span className="reminder-date">{r.next_due ? fmtDate(r.next_due) : "—"}</span>
                <span className="freq-tag">{t("lead_days", { n: r.days_before })}</span>
                <button type="button" className="reminder-edit" aria-label={t("edit")} onClick={(event) => { event.stopPropagation(); setEditing(r); }}>✎</button>
              </div>
            ))}
          </div>
        )}
      </div>

      {editing && (
        <ReminderModal
          reminder={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            toast(t("saved"));
            reminders.reload();
          }}
          onDeleted={() => {
            setEditing(null);
            toast(t("deleted"));
            reminders.reload();
          }}
        />
      )}
    </ViewFrame>
  );
}

function ReminderModal({
  reminder,
  onClose,
  onSaved,
  onDeleted,
}: {
  reminder: Reminder | null;
  onClose: () => void;
  onSaved: () => void;
  onDeleted: () => void;
}) {
  const toast = useToast();
  const [frequency, setFrequency] = useState<Frequency>(reminder?.frequency ?? "monthly");
  const [busy, setBusy] = useState(false);

  return (
    <Modal
      title={reminder ? t("edit_reminder") : t("new_reminder")}
      onClose={onClose}
      busy={busy}
      actionsLeading={reminder && (
        <button type="button" className="btn danger" onClick={async () => {
          await api.deleteReminder(reminder.id);
          onDeleted();
        }}>{t("delete")}</button>
      )}
      onSubmit={async (form) => {
        setBusy(true);
        try {
          const payload = buildPayload(form, frequency);
          if (reminder) await api.replaceReminder(reminder.id, payload);
          else await api.createReminder(payload);
          onSaved();
        } catch {
          toast(t("save_failed"));
        } finally {
          setBusy(false);
        }
      }}
    >
      <Field label={t("item_name")}>
        <input name="title" required maxLength={200} defaultValue={reminder?.title ?? ""} />
      </Field>

      <Field label={t("freq")}>
        <select
          name="frequency"
          value={frequency}
          onChange={(e) => setFrequency(e.target.value as Frequency)}
        >
          <option value="monthly">{t("freq_monthly")}</option>
          <option value="yearly">{t("freq_yearly")}</option>
          <option value="once">{t("freq_once")}</option>
        </select>
      </Field>

      {/* Only the fields the chosen frequency uses. Driven by state rather than by
          toggling `hidden` on DOM nodes, so what is on screen and what gets submitted
          cannot disagree. */}
      <Field label={t("day_of_month")} hidden={frequency === "once"}>
        <input
          name="day_of_month"
          type="number"
          min={1}
          max={31}
          defaultValue={reminder?.day_of_month ?? 1}
        />
      </Field>

      <Field label={t("month_of_year")} hidden={frequency !== "yearly"}>
        <input
          name="month_of_year"
          type="number"
          min={1}
          max={12}
          defaultValue={reminder?.month_of_year ?? 1}
        />
      </Field>

      <Field label={t("on_date")} hidden={frequency !== "once"}>
        <input name="on_date" type="date" defaultValue={reminder?.on_date ?? todayISO()} />
      </Field>

      <Field label={t("days_before")}>
        <input
          name="days_before"
          type="number"
          min={0}
          max={365}
          defaultValue={reminder?.days_before ?? 0}
        />
      </Field>

      <Field label={t("note")}>
        <input name="note" maxLength={500} defaultValue={reminder?.note ?? ""} />
      </Field>

      <div className="field">
        <label>
          <input type="checkbox" name="active" defaultChecked={reminder?.active !== false} />{" "}
          {t("active")}
        </label>
      </div>
    </Modal>
  );
}

function reminderStatus(r: Reminder): string {
  if (!r.active) return t("inactive");
  if (r.days_until_due === null) return "—";
  if (r.days_until_due < 0) return t("overdue_days", { n: Math.abs(r.days_until_due) });
  if (r.days_until_due === 0) return t("due_today");
  return t("days_later", { n: r.days_until_due });
}

function reminderStatusClass(r: Reminder): "overdue" | "today" | "later" | "off" {
  if (!r.active) return "off";
  if ((r.days_until_due ?? 0) < 0) return "overdue";
  if (r.days_until_due === 0) return "today";
  return "later";
}

function frequencyDescription(r: Reminder, labels: Record<Frequency, string>): string {
  if (r.frequency === "once") return `${labels.once} ${r.on_date ? fmtDate(r.on_date) : ""}`;
  if (r.frequency === "monthly") return `${labels.monthly} ${r.day_of_month ?? ""}${t("day_suffix")}`;
  return `${labels.yearly} ${r.month_of_year ?? ""}/${r.day_of_month ?? ""}`;
}

/**
 * Build the payload the API's cross-field rules accept.
 *
 * ReminderIn rejects a monthly reminder with no day_of_month, and a once reminder with
 * no on_date. Sending every field regardless would attach a day-of-month to a one-off,
 * so the fields that do not apply are omitted rather than sent as null — which is why
 * `ReminderIn` declares them optional rather than nullable.
 */
function buildPayload(form: FormData, frequency: Frequency): ReminderIn {
  const base: ReminderIn = {
    title: String(form.get("title") ?? ""),
    frequency,
    days_before: Number(form.get("days_before") ?? 0),
    note: String(form.get("note") ?? "") || null,
    active: form.get("active") === "on",
  };

  if (frequency === "once") return { ...base, on_date: String(form.get("on_date")) };
  if (frequency === "monthly") return { ...base, day_of_month: Number(form.get("day_of_month")) };
  return {
    ...base,
    day_of_month: Number(form.get("day_of_month")),
    month_of_year: Number(form.get("month_of_year")),
  };
}
