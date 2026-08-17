import { useState } from "react";

import { ConfirmDelete, Field, Modal } from "../components/Modal";
import { ViewFrame } from "../components/ViewFrame";
import { ApiError, api } from "../lib/api";
import { useToast } from "../lib/context";
import { t } from "../lib/i18n";
import { useMediaQuery } from "../lib/useMediaQuery";
import { useResource } from "../lib/useResource";
import { useSortable } from "../lib/useSortable";
import type { Sortable } from "../lib/useSortable";
import type { ListRow, ListTable } from "../lib/types";

export function Lists() {
  const toast = useToast();
  const lists = useResource(() => api.lists());
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<ListTable | null | "new">(null);
  const [addingRow, setAddingRow] = useState(false);
  const [confirming, setConfirming] = useState(false);

  const all = lists.data ?? [];
  const active = all.find((l) => l.id === selectedId) ?? all[0];

  const q = search.trim().toLowerCase();
  const rows = (active?.items ?? []).filter(
    (r) => !q || r.values.some((v) => v.toLowerCase().includes(q)),
  );

  return (
    <ViewFrame title={t("lists_title")} subtitle={t("lists_sub")} resources={[lists]}>
      {all.length === 0 && (
        <div className="card">
          <button className="btn" onClick={() => setEditing("new")}>
            {t("new_list")}
          </button>
          <div className="empty-note">{t("no_lists")}</div>
        </div>
      )}

      {active && (
        <div className="lists-layout">
          <ListNav
            lists={all}
            activeId={active.id}
            onSelect={(id) => {
              setSelectedId(id);
              setSearch("");
            }}
            onNew={() => setEditing("new")}
            onReordered={() => lists.reload()}
            patch={lists.patch}
          />

          <div className="list-main card">
            <div className="list-toolbar">
              {/* Controlled by React state, so the value survives re-renders. The
                  previous version rebuilt the DOM on each keystroke and had to restore
                  focus and caret position by hand afterwards. */}
              <input
                className="list-search"
                type="search"
                placeholder={t("search")}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
              {/* Opens a form rather than appending a blank row to the table.
                  Appending meant the new row arrived at the bottom of a 46-row list,
                  off screen, and you then had to find it and fill it cell by cell —
                  with each cell saving on its own request. A dialog puts the fields in
                  front of you, labelled, and writes the row once. */}
              <button type="button" className="btn" onClick={() => setAddingRow(true)}>
                {t("add_row")}
              </button>
              {/* Same size as the button beside them. Hierarchy comes from fill and
                  colour — a filled primary, an outlined secondary, a red destructive —
                  not from making the less important ones shorter. */}
              <button type="button" className="btn subtle" onClick={() => setEditing(active)}>
                {t("list_settings_button")}
              </button>
              <span className="list-count">{t("list_items_count", { n: active.items.length })}</span>
            </div>

            <RowList
              key={active.id}
              list={active}
              rows={rows}
              filtered={q.length > 0}
              onChanged={() => lists.reload()}
              patch={lists.patch}
            />
          </div>
        </div>
      )}

      {editing && (
        <ListModal
          list={editing === "new" ? null : editing}
          onClose={() => setEditing(null)}
          {...(editing === "new"
            ? {}
            : {
                onDelete: () => {
                  setEditing(null);
                  setConfirming(true);
                },
              })}
          onSaved={() => {
            setEditing(null);
            toast(t("saved"));
            lists.reload();
          }}
        />
      )}

      {addingRow && active && (
        <RowModal
          listId={active.id}
          listName={active.name}
          columns={active.columns}
          onClose={() => setAddingRow(false)}
          onSaved={() => {
            setAddingRow(false);
            toast(t("saved"));
            lists.reload();
          }}
        />
      )}

      {confirming && active && (
        <ConfirmDelete
          what={active.name}
          onCancel={() => setConfirming(false)}
          onConfirm={async () => {
            await api.deleteList(active.id);
            setConfirming(false);
            setSelectedId(null);
            toast(t("deleted"));
            lists.reload();
          }}
        />
      )}
    </ViewFrame>
  );
}

/**
 * The sidebar of lists, reorderable by dragging.
 *
 * The axis changes with the layout: the nav is a column on a desktop and a scrolling
 * row on a phone, and a reorder gesture that goes the wrong way is worse than none.
 * `useSortable` takes the axis, and `matchMedia` decides which — matching the same
 * 768px breakpoint the stylesheet uses.
 *
 * Each entry is a wrapper holding two buttons rather than one button containing a
 * handle: a button inside a button is invalid HTML, and browsers recover from it in
 * ways that break the inner one's click.
 */
function ListNav({
  lists,
  activeId,
  onSelect,
  onNew,
  onReordered,
  patch,
}: {
  lists: ListTable[];
  activeId: number;
  onSelect: (id: number) => void;
  onNew: () => void;
  onReordered: () => void;
  patch: (update: (current: ListTable[]) => ListTable[]) => void;
}) {
  const toast = useToast();
  const horizontal = useMediaQuery("(max-width: 768px)");

  const commit = async (from: number, to: number) => {
    const next = [...lists];
    const [moved] = next.splice(from, 1);
    if (!moved) return;
    next.splice(to, 0, moved);

    // On screen first. The user has already watched the item land where they put it;
    // waiting for the server before it moves makes the drag feel like it failed.
    patch(() => next);
    try {
      await api.reorderLists(next.map((l) => l.id));
    } catch (err) {
      toast(err instanceof ApiError ? err.detail : t("save_failed"));
    } finally {
      onReordered();
    }
  };

  const sortable = useSortable(lists.length, commit, horizontal ? "x" : "y");
  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= lists.length) return;
    void commit(index, target);
  };

  return (
    <aside className="list-sidebar">
      <p className="list-drag-hint">{t("list_drag_hint")}</p>
      <div className="list-nav" {...sortable.containerProps}>
      {lists.map((l, index) => {
        const rowProps = sortable.rowProps(index);
        return (
          <div
            className={`list-nav-item ${sortable.state.from === index ? "dragging" : ""}`}
            key={l.id}
            ref={rowProps.ref}
            style={rowProps.style}
          >
            <button
              type="button"
              className="drag-handle"
              aria-label={t("reorder")}
              title={t("reorder_hint")}
              {...sortable.handleProps(index)}
            >
              ⠿
            </button>
            <button
              type="button"
              className={`list-nav-btn ${l.id === activeId ? "active" : ""}`}
              aria-current={l.id === activeId ? "true" : undefined}
              onClick={() => onSelect(l.id)}
            >
              <span className="list-nav-icon">{l.icon ?? "📄"}</span>
              <span className="list-nav-label">{l.name}</span>
              <span className="cnt">{l.items.length}</span>
            </button>
            <div className="list-nav-controls">
              <button
                type="button"
                className="list-order-button"
                aria-label={t("list_move_up")}
                title={t("list_move_up")}
                disabled={index === 0}
                onClick={() => move(index, -1)}
              >
                ↑
              </button>
              <button
                type="button"
                className="list-order-button"
                aria-label={t("list_move_down")}
                title={t("list_move_down")}
                disabled={index === lists.length - 1}
                onClick={() => move(index, 1)}
              >
                ↓
              </button>
            </div>
          </div>
        );
      })}
      </div>
      <button type="button" className="list-new-button" onClick={onNew}>
        {t("new_list")}
      </button>
    </aside>
  );
}

/**
 * A form built from the list's own columns.
 *
 * The fields are whatever the list says they are, which is the point of the feature:
 * a list of warranties and a list of recipes have nothing in common except that their
 * owner defined the headings. Reading them from `columns` means this dialog never
 * needs to know what any particular list is for.
 */
function RowModal({
  listId,
  listName,
  columns,
  onClose,
  onSaved,
}: {
  listId: number;
  listName: string;
  columns: string[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <Modal
      title={`${t("new_list_item")} — ${listName}`}
      onClose={onClose}
      busy={busy}
      onSubmit={async (form) => {
        setBusy(true);
        setError(null);
        // Positional, and every column contributes exactly one value — including the
        // ones left blank. The API rejects a row whose length does not match the
        // headings, and reading the fields by index is what guarantees it never does.
        const values = columns.map((_, i) => String(form.get(`col-${i}`) ?? ""));
        try {
          await api.createRow(listId, values);
          onSaved();
        } catch (err) {
          setError(err instanceof ApiError ? err.detail : t("save_failed"));
          toast(t("save_failed"));
        } finally {
          setBusy(false);
        }
      }}
    >
      {error && <p className="auth-error">{error}</p>}
      {columns.map((column, i) => (
        <Field key={`${column}${i}`} label={column}>
          {/* autoFocus on the first field only: a dialog that opens with the cursor
              already in it saves a click every single time. */}
          <input name={`col-${i}`} maxLength={500} autoFocus={i === 0} />
        </Field>
      ))}
    </Modal>
  );
}

/**
 * The rows, as a grid that becomes a stack of cards on a narrow screen.
 *
 * Not a `<table>`. A table with seven columns cannot be made to work at 375px — it
 * either scrolls sideways, which hides the column you are looking for, or it squeezes
 * cells until nothing is legible. CSS grid gives the same aligned columns on a wide
 * screen and lets each row become a labelled card on a phone, from one piece of markup.
 * The headings are a `role="row"` of `role="columnheader"` so the structure is still
 * announced as a table to a screen reader.
 */
function RowList({
  list,
  rows,
  filtered,
  onChanged,
  patch,
}: {
  list: ListTable;
  rows: ListRow[];
  filtered: boolean;
  onChanged: () => void;
  patch: (update: (current: ListTable[]) => ListTable[]) => void;
}) {
  const toast = useToast();

  const commit = async (from: number, to: number) => {
    const next = [...rows];
    const [moved] = next.splice(from, 1);
    if (!moved) return;
    next.splice(to, 0, moved);

    // Show the new order immediately; the server call follows. Reordering is a gesture
    // whose result the user has already seen with their own hands — waiting for a round
    // trip before the row lands makes the drag feel broken rather than careful.
    patch((lists) =>
      lists.map((l) => (l.id === list.id ? { ...l, items: next } : l)),
    );

    try {
      await api.reorderRows(list.id, next.map((r) => r.id));
    } catch (err) {
      toast(err instanceof ApiError ? err.detail : t("save_failed"));
    } finally {
      onChanged();
    }
  };

  // Dragging a filtered view would reorder rows against positions the user cannot see,
  // so the handles are hidden while a search is active rather than doing something
  // surprising with the hidden ones.
  const sortable = useSortable(filtered ? 0 : rows.length, commit);

  // A list can have arbitrary columns, but money and dates need far less horizontal
  // room than a payment method or note. Giving those familiar headings a smaller
  // track leaves text columns wide enough to wrap naturally instead of clipping.
  const columnTemplate = `28px ${list.columns.map(listColumnWidth).join(" ")} 44px`;

  return (
    <div className="rowgrid-wrap">
      <div className="rowgrid" role="table" style={{ ["--cols" as string]: columnTemplate }}>
        <div className="rowgrid-head" role="row">
          <span role="columnheader" aria-label={t("reorder")} />
          {list.columns.map((c, i) => (
            <span role="columnheader" key={`${c}${i}`}>
              {c}
            </span>
          ))}
          <span role="columnheader" />
        </div>

        {rows.length === 0 && (
          <div className="empty-note">{filtered ? t("no_match") : t("no_rows")}</div>
        )}

        <div className="rowgrid-body" {...sortable.containerProps}>
          {rows.map((row, index) => (
            <Row
              key={row.id}
              listId={list.id}
              row={row}
              columns={list.columns}
              onChanged={onChanged}
              sortable={filtered ? null : sortable}
              index={index}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function listColumnWidth(column: string): string {
  const label = column.toLowerCase();
  if (/金額|費用|amount|price|usd|date|日期|到期|月份/.test(label)) {
    return "minmax(76px, 0.65fr)";
  }
  if (/備註|note|說明|details|comment/.test(label)) return "minmax(150px, 1.45fr)";
  return "minmax(120px, 1fr)";
}

/**
 * One row, holding its own draft state.
 *
 * Local state per row rather than one draft for the whole list: a keystroke re-renders
 * this row instead of all 46. Saved on blur — one request per edit rather than per
 * character, with no debounce timer to reason about.
 */
function Row({
  listId,
  row,
  columns,
  onChanged,
  sortable,
  index,
}: {
  listId: number;
  row: ListRow;
  columns: string[];
  onChanged: () => void;
  sortable: Sortable | null;
  index: number;
}) {
  const [confirming, setConfirming] = useState(false);
  const [editing, setEditing] = useState(false);

  const dragging = sortable?.state.from === index;
  const rowProps = sortable?.rowProps(index);

  return (
    <>
      <div
        className={`rowgrid-row ${dragging ? "dragging" : ""}`}
        role="row"
        ref={rowProps?.ref}
        style={rowProps?.style}
      >
        {sortable ? (
          <button
            className="drag-handle"
            aria-label={t("reorder")}
            title={t("reorder_hint")}
            {...sortable.handleProps(index)}
          >
            ⠿
          </button>
        ) : (
          <span />
        )}

        {row.values.map((value, i) => (
          <div className="cell" key={i} role="cell">
            {/* The column name is a visible label on a phone, where there is no header
                row above to read it from, and visually hidden on a wide screen where
                there is. Same markup, one CSS rule apart. */}
            <span className="cell-label">{columns[i] ?? ""}</span>
            <span className={`cell-value ${value ? "" : "empty"}`}>{value || "—"}</span>
          </div>
        ))}

        <button className="row-edit-button" onClick={() => setEditing(true)} aria-label={t("edit")} title={t("edit")} role="cell">
          ✎
        </button>
      </div>

      {editing && (
        <EditRowModal
          listId={listId}
          row={row}
          columns={columns}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            onChanged();
          }}
          onDelete={() => {
            setEditing(false);
            setConfirming(true);
          }}
        />
      )}
      {confirming && (
        <ConfirmDelete
          what={row.values.find((v) => v.trim()) ?? "—"}
          onCancel={() => setConfirming(false)}
          onConfirm={async () => {
            await api.deleteRow(listId, row.id);
            setConfirming(false);
            onChanged();
          }}
        />
      )}
    </>
  );
}

function EditRowModal({
  listId,
  row,
  columns,
  onClose,
  onSaved,
  onDelete,
}: {
  listId: number;
  row: ListRow;
  columns: string[];
  onClose: () => void;
  onSaved: () => void;
  onDelete: () => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <Modal
      title={t("edit")}
      onClose={onClose}
      busy={busy}
      actionsLeading={<button type="button" className="btn danger" onClick={onDelete}>{t("delete")}</button>}
      onSubmit={async (form) => {
        setBusy(true);
        setError(null);
        const values = columns.map((_, i) => String(form.get(`col-${i}`) ?? ""));
        try {
          await api.replaceRow(listId, row.id, values);
          toast(t("saved"));
          onSaved();
        } catch (err) {
          setError(err instanceof ApiError ? err.detail : t("save_failed"));
          toast(t("save_failed"));
        } finally {
          setBusy(false);
        }
      }}
    >
      {error && <p className="auth-error">{error}</p>}
      {columns.map((column, i) => (
        <Field key={`${column}${i}`} label={column}>
          <textarea name={`col-${i}`} rows={Math.max(1, row.values[i]?.split(/\r?\n/).length ?? 1)} defaultValue={row.values[i] ?? ""} maxLength={500} />
        </Field>
      ))}
    </Modal>
  );
}

function ListModal({
  list,
  onClose,
  onDelete,
  onSaved,
}: {
  list: ListTable | null;
  onClose: () => void;
  onDelete?: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <Modal
      title={list ? `${t("list_settings")} — ${list.name}` : t("new_list")}
      onClose={onClose}
      busy={busy}
      submitLabel={list ? t("save") : t("create")}
      onSubmit={async (form) => {
        setBusy(true);
        setError(null);
        const payload = {
          name: String(form.get("name") ?? ""),
          icon: String(form.get("icon") ?? "") || null,
          columns: String(form.get("columns") ?? "")
            .split(",")
            .map((c) => c.trim())
            .filter(Boolean),
          position: list?.position ?? 999,
        };
        try {
          if (list) await api.replaceList(list.id, payload);
          else await api.createList(payload);
          onSaved();
        } catch (err) {
          // 409 for a duplicate name, or for changing the column count while rows
          // exist. Both are things the user can fix, so they belong in the dialog.
          setError(err instanceof ApiError ? err.detail : t("save_failed"));
          toast(t("save_failed"));
        } finally {
          setBusy(false);
        }
      }}
    >
      {error && <p className="auth-error">{error}</p>}

      <Field label={t("list_name")}>
        <input name="name" required maxLength={120} defaultValue={list?.name ?? ""} />
      </Field>
      <Field label={t("list_icon")}>
        <input name="icon" maxLength={16} defaultValue={list?.icon ?? "📄"} />
      </Field>
      <Field label={t("list_columns")}>
        <input
          name="columns"
          required
          defaultValue={(list?.columns ?? [t("item_name"), t("note")]).join(", ")}
        />
        {list && list.items.length > 0 && (
          <div className="freq-tag" style={{ marginTop: 4 }}>
            {t("columns_locked", { n: list.items.length })}
          </div>
        )}
      </Field>
      {list && onDelete && (
        <button type="button" className="btn danger list-delete-button" onClick={onDelete}>
          {t("delete_whole_list")}
        </button>
      )}
    </Modal>
  );
}
