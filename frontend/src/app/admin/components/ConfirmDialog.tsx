"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { CheckCircle2, CircleAlert, X } from "lucide-react";

type ConfirmDialogProps = {
  title: string;
  className?: string;
  description: ReactNode;
  confirmLabel: string;
  busy?: boolean;
  confirmDisabled?: boolean;
  danger?: boolean;
  safeDestructive?: boolean;
  children?: ReactNode;
  extraActions?: ReactNode;
  onCancel: () => void;
  onConfirm: () => void;
};

export function ConfirmDialog({
  title,
  className = "",
  description,
  confirmLabel,
  busy = false,
  confirmDisabled = false,
  danger = false,
  safeDestructive = false,
  children,
  extraActions,
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  const panel = useRef<HTMLElement>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);
  const current = useRef({ busy, onCancel });
  current.current = { busy, onCancel };
  useEffect(() => {
    const trigger = document.activeElement as HTMLElement | null;
    cancelButton.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopImmediatePropagation();
        if (!current.current.busy) current.current.onCancel();
      }
      if (event.key !== "Tab") return;
      const items = Array.from(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex="0"]') ?? []).filter(item => item.getClientRects().length);
      const first = items[0], last = items.at(-1);
      if (!first) { event.preventDefault(); panel.current?.focus(); }
      else if (!panel.current?.contains(document.activeElement) || (!event.shiftKey && document.activeElement === last)) { event.preventDefault(); first.focus(); }
      else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      if (trigger?.isConnected) trigger.focus({ preventScroll:true });
    };
  }, []);
  return (
    <div
      className="modal-backdrop duplicate-backdrop"
      role="presentation"
      onMouseDown={() => { if (!busy) onCancel(); }}
    >
      <section
        ref={panel}
        tabIndex={-1}
        className={`set-action-dialog crm-confirm-dialog ${className}`}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button
          className="dialog-close"
          disabled={busy}
          onClick={onCancel}
          title="Закрыть"
        >
          <X size={18} />
        </button>
        <div className={danger ? "duplicate-icon" : "dialog-icon"}>
          {danger ? <CircleAlert size={23} /> : <CheckCircle2 size={22} />}
        </div>
        
        <h2 id="confirm-dialog-title">{title}</h2>
        <p>{description}</p>
        {children}
        <div className="dialog-actions">
          <button
            ref={cancelButton}
            className={
              safeDestructive ? "reset-cancel-button" : "secondary-button"
            }
            autoFocus={safeDestructive}
            disabled={busy}
            onClick={onCancel}
          >
            Отмена
          </button>
          <button
            className={
              safeDestructive
                ? "reset-confirm-button"
                : danger
                  ? "overflow-confirm-button"
                  : "confirm-transfer-button"
            }
            disabled={busy || confirmDisabled}
            onClick={onConfirm}
          >
            {busy ? "Выполняем..." : confirmLabel}
          </button>
          {extraActions}
        </div>
      </section>
    </div>
  );
}
