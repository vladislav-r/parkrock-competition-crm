"use client";

import { useEffect, useState } from "react";
import { LogOut, MoreVertical, Pencil, QrCode, Settings, ShieldOff } from "lucide-react";
import { changeQrAccess, endUserSession, issueQrCards, type QrCards, type StaffUser, type UserAccess } from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";
import { CrmLogo } from "./CrmLogo";
import "./user-access.css";

export type AccessAction = { kind: "issue" | "settings" | "revoke" | "end"; users: Array<{ user: StaffUser; access: UserAccess }> };

export function StaffActions({ user, access, administrator, onEdit, onAction }: {
  user: StaffUser; access?: UserAccess; administrator: boolean; onEdit: () => void; onAction: (action: AccessAction) => void;
}) {
  const popupId = `staff-actions-${user.id}`;
  function act(kind: AccessAction["kind"]) {
    document.getElementById(popupId)?.hidePopover();
    if (access) onAction({ kind, users: [{ user, access }] });
  }
  return <div className="staff-actions">
    <button className="icon-button" aria-label={`Действия пользователя ${user.full_name}`} popoverTarget={popupId} onClick={event => {
      const bounds = event.currentTarget.getBoundingClientRect();
      const popup = document.getElementById(popupId);
      if (popup) {
        popup.style.left = `${Math.max(8, Math.min(bounds.right - 245, window.innerWidth - 253))}px`;
        popup.style.top = `${Math.max(8, Math.min(bounds.bottom + 5, window.innerHeight - 285))}px`;
      }
    }}><MoreVertical size={18}/></button>
    <div id={popupId} popover="auto" className="staff-actions-popup">
      <button onClick={() => { document.getElementById(popupId)?.hidePopover(); onEdit(); }}><Pencil size={16}/>Редактировать</button>
      {administrator && <>
        <button disabled={!access?.session_id} onClick={() => act("end")}><LogOut size={16}/>Завершить сеанс</button>
        <button disabled={!access || !user.is_active} onClick={() => act("issue")}><QrCode size={16}/>{access?.qr_enabled ? "Перевыпустить QR" : "Выпустить QR"}</button>
        <button disabled={!access?.qr_enabled} onClick={() => act("revoke")}><ShieldOff size={16}/>Отозвать QR</button>
        <button disabled={!access} onClick={() => act("settings")}><Settings size={16}/>Настройки QR</button>
      </>}
    </div>
  </div>;
}

export function UserAccessDialog({ token, action, onClose, onChanged }: { token: string; action: AccessAction; onClose: () => void; onChanged: () => void }) {
  const first = action.users[0];
  const [hours, setHours] = useState(String(first.access.qr_session_hours));
  const [endSession, setEndSession] = useState(false);
  const [operationId, setOperationId] = useState(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [cards, setCards] = useState<QrCards | null>(null);
  const [pdfUrl, setPdfUrl] = useState("");
  useEffect(() => {
    if (!cards) return;
    const data = Uint8Array.from(atob(cards.pdf_base64), char => char.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
    setPdfUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [cards]);
  const replacing = action.users.some(row => row.access.qr_enabled);
  const title = cards ? "QR-карточки готовы" : action.kind === "settings" ? "Настройки QR" : action.kind === "revoke" ? "Отозвать QR" : action.kind === "end" ? "Завершить сеанс" : replacing ? "Перевыпустить QR" : "Выпустить QR";
  const confirmLabel = cards ? "Открыть для печати" : action.kind === "settings" ? "Сохранить" : title;
  async function apply() {
    if (cards) { const view = window.open(pdfUrl, "_blank"); if (view) view.opener = null; else setError("Разрешите открытие вкладки для печати или скачайте PDF."); return; }
    if (busy) return;
    setBusy(true); setError("");
    try {
      if (action.kind === "issue") {
        const result = await issueQrCards(token, action.users.map(row => ({ user_id: row.user.id, expected_version: row.access.version })), endSession, operationId);
        // If this includes our own session, save the cards before the next heartbeat logs us out.
        if (endSession) {
          const url = URL.createObjectURL(new Blob([Uint8Array.from(atob(result.pdf_base64), char => char.charCodeAt(0))], { type: "application/pdf" }));
          const link = document.createElement("a"); link.href = url; link.download = "ParkRock — персональные QR.pdf";
          document.body.appendChild(link); link.click(); link.remove();
          window.setTimeout(() => URL.revokeObjectURL(url), 60000);
        }
        setCards(result);
      } else if (action.kind === "end") {
        await endUserSession(token, first.user.id, first.access.session_id!, operationId);
      } else {
        await changeQrAccess(token, first.user.id, action.kind, { expected_version: first.access.version, qr_session_hours: Number(hours), end_session: endSession }, operationId);
      }
      onChanged();
      if (action.kind !== "issue") onClose();
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось выполнить действие"); onChanged(); }
    finally { setBusy(false); }
  }
  return <ConfirmDialog className="user-access-dialog" title={title} description={action.users.length === 1 ? first.user.full_name : `Выбрано сотрудников: ${action.users.length}`}
    busy={busy} confirmLabel={confirmLabel} cancelLabel={cards ? "Закрыть" : "Отмена"} confirmDisabled={cards ? !pdfUrl : action.kind === "settings" && (!Number.isInteger(Number(hours)) || Number(hours) < 1 || Number(hours) > 168)}
    onConfirm={() => void apply()} onCancel={onClose}
    extraActions={cards && <a className="secondary-button" href={pdfUrl} download="ParkRock — персональные QR.pdf">Скачать PDF</a>}>
    {cards ? <>
      <p>Сохраните PDF для повторной печати. После закрытия этого окна карточки можно получить только перевыпуском QR.</p>
      <div className="qr-cards-preview">{cards.cards.map(card => <article className="qr-card" key={card.user_id}>
        <CrmLogo/><span>{card.full_name}</span>
        <img src={`data:image/svg+xml;base64,${card.svg_base64}`} alt={`Персональный QR: ${card.full_name}`} width={180} height={180}/>
        <span>{card.role_label}</span><small>Личный ключ входа · Не передавайте другим</small>
      </article>)}</div>
    </> : action.kind === "settings" ? <>
      <label className="qr-hours-label">Длительность сеанса, часов<input type="number" min="1" max="168" step="1" value={hours} onChange={event => { setHours(event.target.value); setOperationId(crypto.randomUUID()); }}/></label>
      <p>От 1 до 168 часов с момента входа. Изменение действует для последующих входов. Сам QR остаётся действительным до отзыва или перевыпуска.</p>
    </> : action.kind === "end" ? <p>Доступ на текущем устройстве будет прекращён. Пользователь сможет войти снова по действующему QR или паролю.</p> : <>
      {action.users.length > 1 && <ul className="qr-selected-users">{action.users.map(row => <li key={row.user.id}>{row.user.full_name}{row.access.qr_enabled ? " — QR будет заменён" : ""}</li>)}</ul>}
      <p>{action.kind === "revoke" ? "Распечатанный QR перестанет работать. Вход по паролю останется доступен." : replacing ? "Прежние QR выбранных сотрудников перестанут работать. Потребуется распечатать новые карточки." : "Будут созданы постоянные персональные QR-коды и PDF для печати на А4."}</p>
      {action.kind === "issue" && typeof window !== "undefined" && ["localhost", "127.0.0.1"].includes(window.location.hostname) && <p>Сейчас открыт локальный адрес. Для входа с телефонов выпускайте карточки на опубликованном сайте.</p>}
      {(action.kind === "revoke" || replacing) && <label className="qr-end-option"><input type="checkbox" checked={endSession} onChange={event => { setEndSession(event.target.checked); setOperationId(crypto.randomUUID()); }}/>Также завершить текущие сеансы</label>}
    </>}
    {error && <div className="error-banner" role="alert">{error}</div>}
  </ConfirmDialog>;
}
