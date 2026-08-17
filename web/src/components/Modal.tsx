import { useEffect, useRef } from "react";
import type { FormEvent, ReactNode } from "react";

import { t } from "../lib/i18n";

interface ModalProps {
  title: string;
  onClose: () => void;
  onSubmit?: (form: FormData) => Promise<void> | void;
  submitLabel?: string;
  busy?: boolean;
  /** Optional destructive or secondary actions that belong on the left of the footer. */
  actionsLeading?: ReactNode;
  children: ReactNode;
}

/**
 * A dialog rendered as part of the tree rather than appended to document.body.
 *
 * The previous implementation created the element imperatively and handed back a
 * `close()` function, which meant every caller had to remember to call it on both the
 * success and the failure path. Here the parent owns a boolean and the dialog exists
 * only while it is true, so "forgot to close it" stops being a thing that can happen.
 */
export function Modal({
  title,
  onClose,
  onSubmit,
  submitLabel,
  busy = false,
  actionsLeading,
  children,
}: ModalProps) {
  const overlay = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    overlay.current?.querySelector<HTMLElement>("input, select, textarea")?.focus();
  }, []);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (onSubmit) await onSubmit(new FormData(e.currentTarget));
  };

  return (
    <div
      className="modal-overlay"
      ref={overlay}
      // Clicking the backdrop closes; clicking inside must not. Comparing the target
      // to the overlay itself is what distinguishes the two.
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <h2>{title}</h2>
        {onSubmit ? (
          <form method="post" action="" onSubmit={handleSubmit}>
            {children}
            <div className="modal-actions">
              {actionsLeading && <div className="modal-actions-leading">{actionsLeading}</div>}
              <div className="modal-actions-primary">
                <button type="button" className="btn" onClick={onClose}>
                  {t("cancel")}
                </button>
                <button type="submit" className="btn primary" disabled={busy}>
                  {submitLabel ?? t("save")}
                </button>
              </div>
            </div>
          </form>
        ) : (
          children
        )}
      </div>
    </div>
  );
}

interface ConfirmProps {
  what: string;
  onCancel: () => void;
  onConfirm: () => void;
}

/** Confirm before anything irreversible. `confirm()` blocks the thread and looks
 *  foreign to the rest of the page. */
export function ConfirmDelete({ what, onCancel, onConfirm }: ConfirmProps) {
  return (
    <Modal title={t("confirm_delete_title")} onClose={onCancel}>
      <p>{t("confirm_delete_body", { what })}</p>
      <div className="modal-actions">
        <button type="button" className="btn" onClick={onCancel}>
          {t("cancel")}
        </button>
        <button type="button" className="btn danger" onClick={onConfirm}>
          {t("delete")}
        </button>
      </div>
    </Modal>
  );
}

/** A labelled input, since every form here is the same shape. */
export function Field({
  label,
  children,
  hidden = false,
}: {
  label: string;
  children: ReactNode;
  hidden?: boolean;
}) {
  return (
    <div className="field" hidden={hidden}>
      <label>{label}</label>
      {children}
    </div>
  );
}
