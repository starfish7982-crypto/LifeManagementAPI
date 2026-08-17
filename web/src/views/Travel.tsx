import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { Field, Modal } from "../components/Modal";
import { ViewFrame } from "../components/ViewFrame";
import { api } from "../lib/api";
import { useToast } from "../lib/context";
import { fmtDate, money, todayISO } from "../lib/format";
import { t } from "../lib/i18n";
import type { CalendarLodgingSuggestion, TravelBenefit, TravelExpense } from "../lib/types";
import { useResource } from "../lib/useResource";

type LodgingDates = { checkIn: string; checkOut: string };
type LodgingFormValues = LodgingDates & {
  name: string;
  address: string;
  confirmationNumber: string;
  phone: string;
  details: string;
};

export function Travel() {
  const toast = useToast();
  const trip = useResource(() => api.trip());
  const benefits = useResource(() => api.travelBenefits());
  const [lodgingDates, setLodgingDates] = useState<LodgingDates | null>(null);
  const [addingBenefit, setAddingBenefit] = useState(false);
  const [editingBenefit, setEditingBenefit] = useState<TravelBenefit | null>(null);
  const [addingExpense, setAddingExpense] = useState(false);
  const [editingExpense, setEditingExpense] = useState<TravelExpense | null>(null);
  const [receiptDraftId, setReceiptDraftId] = useState<number | null>(null);
  const [scanningReceipt, setScanningReceipt] = useState(false);
  const receiptInput = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState("");

  const data = trip.data;
  const packing = data?.packing ?? [];
  const packed = packing.filter((item) => item.done).length;
  const expenses = data?.expenses ?? [];
  const expenseTotal = expenses.reduce((sum, expense) => sum + Number(expense.amount), 0);

  const saveTrip = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const startDate = String(form.get("start_date") ?? "") || null;
    const endDate = String(form.get("end_date") ?? "") || null;
    const saved = await api.setTrip({
      start_date: startDate,
      end_date: endDate,
      license_plate: String(form.get("license_plate") ?? "") || null,
    });
    toast(t("saved"));
    trip.reload();

    // Dates are saved before asking about lodgings, so a dismissed lodging dialog
    // never risks losing the trip itself.  Opening only when the range changed avoids
    // interrupting an edit that merely changes the licence plate.
    if (
      saved.start_date &&
      saved.end_date &&
      (saved.start_date !== data?.start_date || saved.end_date !== data?.end_date)
    ) {
      setLodgingDates({ checkIn: saved.start_date, checkOut: saved.end_date });
    }
  };

  const addPacking = async (e: FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    await api.addPacking(text);
    trip.reload();
  };

  return (
    <ViewFrame title={t("travel_title")} subtitle={t("travel_sub")} resources={[trip, benefits]}>
      <div className="travel-grid">
        <section className="card travel-info-card">
          <h2>🗺️ {t("trip_details")}</h2>
          <form onSubmit={saveTrip} key={data?.updated_at ?? "empty"}>
            <Field label={t("trip_dates")}>
              <div className="travel-date-fields">
                <input type="date" name="start_date" defaultValue={data?.start_date ?? ""} />
                <input type="date" name="end_date" defaultValue={data?.end_date ?? ""} />
              </div>
            </Field>
            <Field label={`🚗 ${t("license_plate")} `}>
              <input name="license_plate" maxLength={32} defaultValue={data?.license_plate ?? ""} />
            </Field>

            <div className="card-head-row travel-lodgings-head">
              <h2>🏨 {t("lodgings", { n: (data?.lodgings ?? []).length })}</h2>
              <button
                type="button"
                className="btn"
                onClick={(event) => {
                  // Read the current form values so dates filled just before opening
                  // the lodging dialog are used immediately, even before saving.
                  const form = event.currentTarget.form;
                  const values = form ? new FormData(form) : null;
                  setLodgingDates({
                    checkIn: String(values?.get("start_date") ?? data?.start_date ?? ""),
                    checkOut: String(values?.get("end_date") ?? data?.end_date ?? ""),
                  });
                }}
              >
                {t("add_lodging")}
              </button>
            </div>

            {(data?.lodgings ?? []).length === 0 && <div className="empty-note">{t("no_lodgings")}</div>}
            {(data?.lodgings ?? []).map((lodging) => (
              <div className="travel-lodging-card" key={lodging.id}>
                <div className="todo-body">
                  <div className="todo-title">{lodging.name}</div>
                  <div className="todo-date">{fmtDate(lodging.check_in)} → {fmtDate(lodging.check_out)}</div>
                  {lodging.address && (
                    <a
                      className="travel-map-link"
                      href={`https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(lodging.address)}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      📍 {lodging.address}
                    </a>
                  )}
                  {lodging.confirmation_number && <div className="todo-note">{t("confirmation_number")}: {lodging.confirmation_number}</div>}
                  {lodging.phone && <div className="todo-note">{t("phone")}: {lodging.phone}</div>}
                  {lodging.details && <div className="todo-note">{lodging.details}</div>}
                </div>
                <button
                  type="button"
                  className="btn danger icon"
                  aria-label={t("delete")}
                  onClick={async () => {
                    await api.deleteLodging(lodging.id);
                    trip.reload();
                  }}
                >
                  ×
                </button>
              </div>
            ))}
            <button type="submit" className="btn primary travel-save">{t("save")}</button>
          </form>
        </section>

        <section className="card travel-packing-card">
          <h2>🎒 {t("packing", { done: packed, total: packing.length })}</h2>
          <form className="shop-add" onSubmit={addPacking}>
            <input
              type="text"
              maxLength={200}
              placeholder={t("packing_placeholder")}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
            <button type="submit" className="btn">{t("add_btn")}</button>
          </form>
          {packing.length === 0 && <div className="empty-note">{t("no_packing")}</div>}
          {packing.map((item) => (
            <div className={`todo-item ${item.done ? "done" : ""}`} key={item.id}>
              <input
                type="checkbox"
                checked={item.done}
                aria-label={item.text}
                onChange={async (e) => {
                  const done = e.target.checked;
                  trip.patch((current) => current === null ? current : {
                    ...current,
                    packing: current.packing.map((row) => row.id === item.id ? { ...row, done } : row),
                  });
                  try {
                    await api.togglePacking(item.id, done);
                  } finally {
                    trip.reload();
                  }
                }}
              />
              <div className="todo-body"><div className="todo-title">{item.text}</div></div>
              <button
                type="button"
                className="btn danger icon"
                aria-label={t("delete")}
                onClick={async () => {
                  await api.deletePacking(item.id);
                  trip.reload();
                }}
              >
                ×
              </button>
            </div>
          ))}
        </section>
      </div>

      <section className="card travel-expenses-card">
        <div className="card-head-row travel-expenses-head">
          <div>
            <h2>{t("travel_expenses", { n: expenses.length })}</h2>
            <div className="travel-expense-total">{t("travel_expense_total")}: {money(expenseTotal, 2)}</div>
          </div>
          <div className="btn-row">
            <input
              ref={receiptInput}
              className="receipt-file-input"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              capture="environment"
              onChange={async (event) => {
                const file = event.currentTarget.files?.[0];
                event.currentTarget.value = "";
                if (!file) return;
                setScanningReceipt(true);
                try {
                  const scanned = await api.scanTravelReceipt(file);
                  setReceiptDraftId(scanned.id);
                  setEditingExpense(scanned);
                  trip.reload();
                } catch (error) {
                  toast(error instanceof Error ? error.message : t("save_failed"));
                } finally {
                  setScanningReceipt(false);
                }
              }}
            />
            <button type="button" className="btn ghost" disabled={scanningReceipt} onClick={() => receiptInput.current?.click()}>
              {scanningReceipt ? t("receipt_scanning") : t("upload_receipt")}
            </button>
            <button type="button" className="btn" onClick={() => setAddingExpense(true)}>{t("add_expense")}</button>
          </div>
        </div>
        {expenses.length === 0 && <div className="empty-note">{t("no_data")}</div>}
        <div className="travel-expense-list">
          {expenses.map((expense) => (
            <button type="button" className="travel-expense-row" key={expense.id} onClick={() => setEditingExpense(expense)}>
              <div className="todo-body">
                <div className="todo-title">{expense.merchant}</div>
                <div className="todo-meta">
                  <span className="todo-date">{fmtDate(expense.spent_at)}</span>
                  {expense.category && <span className="todo-src">{expense.category}</span>}
                  {expense.has_receipt && <span className="todo-src">📎 {t("receipt_attached")}</span>}
                </div>
                {expense.note && <div className="todo-note">{expense.note}</div>}
              </div>
              <strong className="travel-expense-amount">{money(expense.amount, 2)}</strong>
            </button>
          ))}
        </div>
      </section>

      <section className="card travel-benefits-card">
        <div className="card-head-row">
          <h2>{t("travel_benefits", { n: (benefits.data ?? []).length })}</h2>
          <button type="button" className="btn" onClick={() => setAddingBenefit(true)}>{t("add_benefit")}</button>
        </div>
        {(benefits.data ?? []).length === 0 && <div className="empty-note">{t("no_data")}</div>}
        {(benefits.data ?? []).map((benefit) => (
          <div className="travel-benefit-row" key={benefit.id}>
            <button
              type="button"
              className="travel-benefit-card"
              onClick={() => setEditingBenefit(benefit)}
              aria-label={t("edit_benefit", { name: benefit.card_name })}
            >
            <div className="todo-body">
              <div className="todo-title">{benefit.card_name}</div>
              {benefit.benefit && <div className="todo-note">{benefit.benefit}</div>}
            </div>
            {benefit.expires_at && <span className="badge later">{t("expires_on", { date: fmtDate(benefit.expires_at) })}</span>}
            </button>
            <button
              type="button"
              className="btn danger icon"
              aria-label={t("delete")}
              onClick={async () => {
                await api.deleteTravelBenefit(benefit.id);
                benefits.reload();
              }}
            >
              ×
            </button>
          </div>
        ))}
      </section>

      {lodgingDates && (
        <LodgingModal
          key={`${lodgingDates.checkIn}-${lodgingDates.checkOut}`}
          dates={lodgingDates}
          onClose={() => setLodgingDates(null)}
          onSaved={async ({ checkOut }) => {
            const tripEnd = data?.end_date ?? lodgingDates.checkOut;
            toast(t("saved"));
            trip.reload();
            // Hotel check-out and the next hotel check-in are the same calendar day.
            // The second dialog is only offered for an actual uncovered tail.
            if (checkOut && tripEnd && checkOut < tripEnd) {
              setLodgingDates({ checkIn: checkOut, checkOut: tripEnd });
            } else {
              setLodgingDates(null);
            }
          }}
        />
      )}
      {(addingBenefit || editingBenefit) && (
        <BenefitModal
          benefit={editingBenefit ?? undefined}
          onClose={() => {
            setAddingBenefit(false);
            setEditingBenefit(null);
          }}
          onSaved={() => {
            setAddingBenefit(false);
            setEditingBenefit(null);
            toast(t("saved"));
            benefits.reload();
          }}
          onDeleted={() => {
            setEditingBenefit(null);
            toast(t("deleted"));
            benefits.reload();
          }}
        />
      )}
      {(addingExpense || editingExpense) && (
        <ExpenseModal
          {...(editingExpense ? { expense: editingExpense } : {})}
          isReceiptDraft={editingExpense?.id === receiptDraftId}
          onClose={async () => {
            if (editingExpense?.id === receiptDraftId) {
              await api.deleteTravelExpense(editingExpense.id);
              trip.reload();
            }
            setAddingExpense(false);
            setEditingExpense(null);
            setReceiptDraftId(null);
          }}
          onSaved={() => {
            setAddingExpense(false);
            setEditingExpense(null);
            setReceiptDraftId(null);
            toast(t("saved"));
            trip.reload();
          }}
          onDeleted={() => {
            setEditingExpense(null);
            setReceiptDraftId(null);
            toast(t("deleted"));
            trip.reload();
          }}
        />
      )}
    </ViewFrame>
  );
}

function ExpenseModal({
  expense,
  isReceiptDraft,
  onClose,
  onSaved,
  onDeleted,
}: {
  expense?: TravelExpense;
  isReceiptDraft: boolean;
  onClose: () => Promise<void> | void;
  onSaved: () => void;
  onDeleted: () => void;
}) {
  return (
    <Modal
      title={t("edit_expense")}
      onClose={() => { void onClose(); }}
      actionsLeading={expense && (
        <button type="button" className="btn danger" onClick={async () => {
          await api.deleteTravelExpense(expense.id);
          onDeleted();
        }}>{t("delete")}</button>
      )}
      onSubmit={async (form) => {
        const payload = {
          merchant: String(form.get("merchant") ?? ""),
          amount: String(form.get("amount") ?? "0"),
          spent_at: String(form.get("spent_at") ?? todayISO()),
          category: String(form.get("category") ?? "") || null,
          note: String(form.get("note") ?? "") || null,
        };
        if (expense) await api.replaceTravelExpense(expense.id, payload);
        else await api.createTravelExpense(payload);
        onSaved();
      }}
    >
      {isReceiptDraft && <p className="receipt-review">{expense?.amount === "0.00" ? t("receipt_ocr_unavailable") : t("receipt_review")}</p>}
      <Field label={t("merchant")}><input name="merchant" required maxLength={200} defaultValue={expense?.merchant ?? ""} /></Field>
      <div className="lodging-date-fields">
        <Field label={t("expense_amount")}><input name="amount" type="number" min="0" step="0.01" required defaultValue={expense?.amount ?? ""} /></Field>
        <Field label={t("expense_date")}><input name="spent_at" type="date" required defaultValue={expense?.spent_at ?? todayISO()} /></Field>
      </div>
      <Field label={t("expense_category")}><input name="category" maxLength={80} defaultValue={expense?.category ?? ""} placeholder="例如: 餐飲、交通、住宿" /></Field>
      <Field label={t("note")}><textarea name="note" rows={3} maxLength={500} defaultValue={expense?.note ?? ""} /></Field>
      {expense?.has_receipt && <div className="receipt-attached-note">📎 {t("receipt_attached")}: {expense.receipt_filename}</div>}
    </Modal>
  );
}

function LodgingModal({
  dates,
  onClose,
  onSaved,
}: {
  dates: LodgingDates;
  onClose: () => void;
  onSaved: (dates: LodgingDates) => Promise<void>;
}) {
  const [values, setValues] = useState<LodgingFormValues>(() => ({
    checkIn: dates.checkIn,
    checkOut: dates.checkOut,
    name: "",
    address: "",
    confirmationNumber: "",
    phone: "",
    details: "",
  }));

  useEffect(() => {
    if (!dates.checkIn || !dates.checkOut) return;
    let active = true;
    void api.lodgingSuggestions(dates.checkIn, dates.checkOut)
      .then(([suggestion]) => {
        if (!active || !suggestion) return;
        setValues((current) => calendarSuggestionIntoForm(current, suggestion));
      })
      // Calendar details are an optional convenience. The normal lodging form should
      // remain usable when a feed is unavailable or does not contain a hotel event.
      .catch(() => undefined);
    return () => { active = false; };
  }, [dates.checkIn, dates.checkOut]);

  return (
    <Modal title={t("add_lodging")} onClose={onClose} onSubmit={async (form) => {
      const checkIn = String(form.get("check_in") ?? "") || "";
      const checkOut = String(form.get("check_out") ?? "") || "";
      await api.addLodging({
        name: String(form.get("name") ?? ""),
        check_in: checkIn || null,
        check_out: checkOut || null,
        address: String(form.get("address") ?? "") || null,
        confirmation_number: String(form.get("confirmation_number") ?? "") || null,
        phone: String(form.get("phone") ?? "") || null,
        details: String(form.get("details") ?? "") || null,
      });
      await onSaved({ checkIn, checkOut });
    }}>
      <div className="lodging-date-fields">
        <Field label={t("check_in")}><input name="check_in" type="date" value={values.checkIn} onChange={(e) => setValues({ ...values, checkIn: e.target.value })} /></Field>
        <Field label={t("check_out")}><input name="check_out" type="date" value={values.checkOut} onChange={(e) => setValues({ ...values, checkOut: e.target.value })} /></Field>
      </div>
      <Field label={t("lodging_name")}><input name="name" required maxLength={300} value={values.name} onChange={(e) => setValues({ ...values, name: e.target.value })} placeholder="例如: Hyatt Regency Toronto" /></Field>
      <Field label={t("address")}><input name="address" maxLength={500} value={values.address} onChange={(e) => setValues({ ...values, address: e.target.value })} placeholder="例如: 123 King St W, Toronto" /></Field>
      <div className="lodging-date-fields">
        <Field label={t("confirmation_number")}><input name="confirmation_number" maxLength={160} value={values.confirmationNumber} onChange={(e) => setValues({ ...values, confirmationNumber: e.target.value })} /></Field>
        <Field label={t("phone")}><input name="phone" maxLength={80} value={values.phone} onChange={(e) => setValues({ ...values, phone: e.target.value })} /></Field>
      </div>
      <Field label={t("lodging_details")}><textarea name="details" maxLength={500} rows={3} value={values.details} onChange={(e) => setValues({ ...values, details: e.target.value })} placeholder="其他飯店資訊或備註..." /></Field>
    </Modal>
  );
}

function calendarSuggestionIntoForm(current: LodgingFormValues, suggestion: CalendarLodgingSuggestion): LodgingFormValues {
  return {
    checkIn: suggestion.check_in ?? current.checkIn,
    checkOut: suggestion.check_out ?? current.checkOut,
    name: suggestion.name || current.name,
    address: suggestion.address ?? current.address,
    confirmationNumber: suggestion.confirmation_number ?? current.confirmationNumber,
    phone: suggestion.phone ?? current.phone,
    details: suggestion.details ?? current.details,
  };
}

function BenefitModal({ benefit, onClose, onSaved, onDeleted }: { benefit?: TravelBenefit | undefined; onClose: () => void; onSaved: () => void; onDeleted: () => void }) {
  return (
    <Modal title={benefit ? t("edit_benefit_title") : t("new_benefit")} onClose={onClose} actionsLeading={benefit && (
      <button type="button" className="btn danger" onClick={async () => {
        await api.deleteTravelBenefit(benefit.id);
        onDeleted();
      }}>{t("delete")}</button>
    )} onSubmit={async (form) => {
      const payload = {
        card_name: String(form.get("card_name") ?? ""),
        benefit: String(form.get("benefit") ?? "") || null,
        expires_at: String(form.get("expires_at") ?? "") || null,
      };
      if (benefit) await api.replaceTravelBenefit(benefit.id, payload);
      else await api.createTravelBenefit(payload);
      onSaved();
    }}>
      <Field label={t("card_name")}><input name="card_name" required maxLength={200} defaultValue={benefit?.card_name ?? ""} placeholder="例如: Chase Sapphire Reserve" /></Field>
      <Field label={t("remaining_benefit")}><textarea name="benefit" rows={4} maxLength={1000} defaultValue={benefit?.benefit ?? ""} placeholder="例如: 免費住宿 1 晚、航空抵用金 $200" /></Field>
      <Field label={t("expires_at")}><input name="expires_at" type="date" defaultValue={benefit?.expires_at ?? ""} /></Field>
    </Modal>
  );
}
