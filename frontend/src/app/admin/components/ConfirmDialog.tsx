import type { ReactNode } from "react";
import { CheckCircle2, CircleAlert, X } from "lucide-react";

type ConfirmDialogProps = {
  title: string;
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
  return (
    <div
      className="modal-backdrop duplicate-backdrop"
      role="presentation"
      onMouseDown={() => { if (!busy) onCancel(); }}
    >
      <section
        className="set-action-dialog"
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
        <div className="eyebrow">Подтверждение действия</div>
        <h2 id="confirm-dialog-title">{title}</h2>
        <p>{description}</p>
        {children}
        <div className="dialog-actions">
          <button
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
