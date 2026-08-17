import { useState } from "react";

import { ConfirmDelete, Field, Modal } from "../components/Modal";
import { ViewFrame } from "../components/ViewFrame";
import { api } from "../lib/api";
import { useToast } from "../lib/context";
import { colourFor, money, monthLabel, todayISO } from "../lib/format";
import { t } from "../lib/i18n";
import { useResource } from "../lib/useResource";
import type { AssetItemIn, Snapshot } from "../lib/types";

// These are the buckets used by the original spreadsheet. Keeping them visible at
// zero makes each monthly snapshot directly comparable instead of making a category
// appear and disappear just because it has no balance that month.
const ASSET_CATEGORIES = [
  "Retirement Accounts",
  "Checking & Saving",
  "ETF",
  "Stock",
  "Crypto Currency",
];

export function Assets() {
  const toast = useToast();
  const snapshots = useResource(() => api.snapshots());
  const categories = useResource(() => api.categories());
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const list = snapshots.data ?? [];
  const activeId = list.some((s) => s.id === selectedId) ? selectedId : (list[0]?.id ?? null);
  const active = useResource(
    () => (activeId === null ? Promise.resolve(null) : api.snapshot(activeId)),
    [activeId],
  );

  const reload = () => {
    snapshots.reload();
    categories.reload();
    active.reload();
  };

  return (
    <ViewFrame
      title={t("assets_title")}
      subtitle={t("assets_sub")}
      resources={[snapshots, categories]}
    >
      <div className="card">
        <div className="assets-toolbar">
          {list.length > 0 && (
            <select
              className="assets-month-select"
              aria-label={t("month_label")}
              value={activeId ?? ""}
              onChange={(e) => setSelectedId(Number(e.target.value))}
            >
              {list.map((s) => (
                <option value={s.id} key={s.id}>
                  {monthLabel(s.month)}
                </option>
              ))}
            </select>
          )}
          <button type="button" className="btn assets-add-month" onClick={() => setAdding(true)}>
            {t("add_month")}
          </button>
        </div>

        {list.length === 0 && <div className="empty-note">{t("no_snapshots")}</div>}

        {active.data && (
          <SnapshotEditor
            snapshot={active.data}
            categories={categories.data ?? []}
            onSaved={reload}
          />
        )}

        {active.data && (
          <button type="button" className="btn danger" onClick={() => setConfirming(true)}>
            {t("delete_month")}
          </button>
        )}
      </div>

      {adding && (
        <MonthModal
          onClose={() => setAdding(false)}
          onCreated={(id) => {
            setAdding(false);
            setSelectedId(id);
            reload();
          }}
        />
      )}

      {confirming && active.data && (
        <ConfirmDelete
          what={monthLabel(active.data.month)}
          onCancel={() => setConfirming(false)}
          onConfirm={async () => {
            await api.deleteSnapshot(active.data!.id);
            setConfirming(false);
            setSelectedId(null);
            toast(t("deleted"));
            reload();
          }}
        />
      )}
    </ViewFrame>
  );
}

/**
 * Editing happens in place: every input is controlled by local state, and the whole
 * snapshot is sent back on blur.
 *
 * The API replaces items wholesale on PUT, so a rename, an addition and a deletion are
 * all the same request. Saving on blur rather than on keystroke means one request per
 * edit instead of one per character, and no debounce timer to reason about.
 */
function SnapshotEditor({
  snapshot,
  categories,
  onSaved,
}: {
  snapshot: Snapshot;
  categories: string[];
  onSaved: () => void;
}) {
  const toast = useToast();
  // Keyed by snapshot id so switching months resets the draft rather than carrying the
  // previous month's edits across.
  const [draft, setDraft] = useState<AssetItemIn[]>(() =>
    snapshot.items.map((i) => ({ name: i.name, category: i.category, amount: i.amount })),
  );
  const [note, setNote] = useState(snapshot.note ?? "");
  const [dirty, setDirty] = useState(false);

  const persist = async (items = draft, nextNote = note) => {
    await api.replaceSnapshot(snapshot.id, {
      month: snapshot.month,
      note: nextNote || null,
      items: items.filter((i) => i.name.trim()),
    });
    setDirty(false);
    toast(t("saved"));
    onSaved();
  };

  // Preserve the order categories are used across the account so the blocks do not
  // jump around between months, then append any this month introduced.
  const order = [...new Set([...ASSET_CATEGORIES, ...categories, ...draft.map((i) => i.category)])];

  const update = (index: number, patch: Partial<AssetItemIn>) => {
    setDraft((rows) => rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));
    setDirty(true);
  };

  return (
    <>
      {order.map((category, ci) => {
        const rows = draft
          .map((row, index) => ({ row, index }))
          .filter(({ row }) => row.category === category);
        const subtotal = rows.reduce((sum, { row }) => sum + Number(row.amount || 0), 0);

        return (
          <div className="cat-block" key={category}>
            <div className="cat-head">
              <span className="cat-name">
                <span className="dot" style={{ background: colourFor(ci) }} />
                {category}
              </span>
              <span className="cat-sum">{money(subtotal)}</span>
            </div>

            {rows.map(({ row, index }) => (
              <div className="asset-row" key={index}>
                <input
                  className="inline-name"
                  value={row.name}
                  aria-label={t("item_name")}
                  onChange={(e) => update(index, { name: e.target.value })}
                  onBlur={() => dirty && persist()}
                />
                <input
                  className="inline-amount"
                  type="number"
                  step="0.01"
                  value={row.amount}
                  aria-label={t("item_amount")}
                  onChange={(e) => update(index, { amount: e.target.value })}
                  onBlur={() => dirty && persist()}
                />
                <button
                  type="button"
                  className="btn danger icon"
                  onClick={() => {
                    const next = draft.filter((_, i) => i !== index);
                    setDraft(next);
                    persist(next);
                  }}
                >
                  ×
                </button>
              </div>
            ))}

            <button
              type="button"
              className="btn subtle small asset-add-item"
              onClick={() => {
                const next = [...draft, { name: t("item_name"), category, amount: "0" }];
                setDraft(next);
                persist(next);
              }}
            >
              {t("add_item")}
            </button>
          </div>
        );
      })}

      <div className="cat-head asset-total">
        <span className="cat-name">{t("total")}</span>
        <span className="cat-sum">{money(draft.reduce((s, i) => s + Number(i.amount || 0), 0), 2)}</span>
      </div>

      <Field label={t("note")}>
        <input
          value={note}
          maxLength={500}
          onChange={(e) => {
            setNote(e.target.value);
            setDirty(true);
          }}
          onBlur={() => dirty && persist(draft, note)}
        />
      </Field>
    </>
  );
}

function MonthModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (id: number) => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <Modal
      title={t("new_month_title")}
      onClose={onClose}
      busy={busy}
      onSubmit={async (form) => {
        setBusy(true);
        setError(null);
        try {
          const created = await api.createSnapshot({
            month: `${String(form.get("month"))}-01`,
            note: String(form.get("note") ?? "") || null,
            items: [],
          });
          onCreated(created.id);
        } catch (err) {
          // A duplicate month is a 409 the user can act on — show it in the dialog
          // rather than closing and leaving them to guess why nothing appeared.
          setError(err instanceof Error ? err.message : t("save_failed"));
          toast(t("save_failed"));
        } finally {
          setBusy(false);
        }
      }}
    >
      {error && <p className="auth-error">{error}</p>}
      <Field label={t("month_label")}>
        <input name="month" type="month" required defaultValue={todayISO().slice(0, 7)} />
      </Field>
      <Field label={t("note")}>
        <input name="note" maxLength={500} />
      </Field>
    </Modal>
  );
}
