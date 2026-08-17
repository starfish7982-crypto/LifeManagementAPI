import { useState } from "react";
import type { FormEvent } from "react";

import { Field, Modal } from "../components/Modal";
import { ViewFrame } from "../components/ViewFrame";
import { api } from "../lib/api";
import { useToast } from "../lib/context";
import { fmtDate } from "../lib/format";
import { t } from "../lib/i18n";
import { useResource } from "../lib/useResource";
import type { Idea } from "../lib/types";

export function Ideas() {
  const toast = useToast();
  const ideas = useResource(() => api.ideas());
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState<Idea | null>(null);

  const list = ideas.data ?? [];

  const add = async (e: FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    await api.createIdea({ text, note: null });
    ideas.reload();
  };

  return (
    <ViewFrame title={`💡 ${t("ideas_title")}`} subtitle={t("ideas_sub")} resources={[ideas]}>
      <div className="card">
        <form className="shop-add" onSubmit={add}>
          <input
            type="text"
            maxLength={500}
            placeholder={t("idea_placeholder")}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <button type="submit" className="btn">
            {t("add_btn")}
          </button>
        </form>

        <div className="page-sub" style={{ margin: "12px 0 8px" }}>
          {t("idea_count", { n: list.length })}
        </div>

        {list.length === 0 && <div className="empty-note">{t("no_ideas")}</div>}

        {list.map((idea) => (
          <button type="button" className="idea-card" key={idea.id} onClick={() => setEditing(idea)}>
            <div className="todo-body">
              <div className="todo-title">{idea.text}</div>
              {idea.note && <div className="todo-note">{idea.note}</div>}
              <div className="todo-meta">
                <span className="freq-tag">🕐 {fmtDate(idea.created_at)}</span>
              </div>
            </div>
          </button>
        ))}
      </div>

      {editing && (
        <Modal
          title={t("edit_idea")}
          onClose={() => setEditing(null)}
          actionsLeading={(
            <button type="button" className="btn danger" onClick={async () => {
              await api.deleteIdea(editing.id);
              setEditing(null);
              toast(t("deleted"));
              ideas.reload();
            }}>{t("delete")}</button>
          )}
          onSubmit={async (form) => {
            await api.replaceIdea(editing.id, {
              text: String(form.get("text") ?? ""),
              note: String(form.get("note") ?? "") || null,
            });
            setEditing(null);
            toast(t("saved"));
            ideas.reload();
          }}
        >
          <Field label={t("idea_text")}>
            <input name="text" required maxLength={500} defaultValue={editing.text} />
          </Field>
          <Field label={t("note")}>
            <textarea name="note" maxLength={1000} rows={5} defaultValue={editing.note ?? ""} />
          </Field>
        </Modal>
      )}
    </ViewFrame>
  );
}
