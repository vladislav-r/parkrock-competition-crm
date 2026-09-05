import { Clock3, X } from "lucide-react";

import type { CompetitionSet, SetPayload } from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";

export type SetEditorState = { mode: "create" } | { mode: "edit"; item: CompetitionSet };
export type SetActionState = { action: "confirm" | "reopen" | "delete"; item: CompetitionSet };

function setTimes(item?: CompetitionSet) {
  const [start = "09:00", end = "12:00"] = item?.time_label.split("-") ?? [];
  return { start, end };
}

export function SetEditorDialog({ state, suggestedNumber, defaultDate, saving, onClose, onSave }: { state: SetEditorState; suggestedNumber: number; defaultDate: string; saving: boolean; onClose: () => void; onSave: (payload: SetPayload) => Promise<void> }) {
  const item = state.mode === "edit" ? state.item : undefined;
  const times = setTimes(item);
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
    <section className="set-editor-dialog" role="dialog" aria-modal="true" aria-labelledby="set-editor-title" onMouseDown={(event) => event.stopPropagation()}>
      <button className="dialog-close" onClick={onClose} title="Закрыть"><X size={18}/></button>
      <div className="dialog-icon"><Clock3 size={22}/></div>
      <div className="eyebrow">Управление сетами</div>
      <h2 id="set-editor-title">{item ? "Редактировать сет" : "Новый сет"}</h2>
      <form onSubmit={(event) => { event.preventDefault(); const data = new FormData(event.currentTarget); void onSave({ name: String(data.get("name")), scheduled_on: String(data.get("scheduled_on")) || null, start_time: String(data.get("start_time")), end_time: String(data.get("end_time")), capacity: Number(data.get("capacity")) }); }}>
        <label className="wide-field">Название<input name="name" defaultValue={item?.name ?? `Сет ${suggestedNumber}`} maxLength={100} required autoFocus/></label>
        <label className="wide-field">Дата<input name="scheduled_on" type="date" defaultValue={item ? item.scheduled_on ?? "" : defaultDate}/><small>Нужна для порядка сетов в многодневном фестивале.</small></label>
        <label>Начало<input name="start_time" type="time" defaultValue={times.start} required/></label>
        <label>Окончание<input name="end_time" type="time" defaultValue={times.end} required/></label>
        <label className="wide-field">Максимальная вместимость<input name="capacity" type="number" min={Math.max(1, item?.participant_count ?? 1)} max="10000" defaultValue={item?.capacity ?? 50} required/><small>{item ? `Сейчас назначено участников: ${item.participant_count}. Вместимость нельзя установить ниже этого числа.` : "Количество участников, которых можно назначить в этот сет."}</small></label>
        <div className="dialog-actions wide-field"><button type="button" className="secondary-button" disabled={saving} onClick={onClose}>Отмена</button><button className="confirm-transfer-button" disabled={saving}>{saving ? "Сохраняем..." : item ? "Сохранить изменения" : "Добавить сет"}</button></div>
      </form>
    </section>
  </div>;
}

export function SetActionDialog({ state, saving, onClose, onConfirm }: { state: SetActionState; saving: boolean; onClose: () => void; onConfirm: () => Promise<void> }) {
  const content = state.action === "confirm"
    ? { title: `Завершить «${state.item.name}»?`, text: "Текущие результаты будут опубликованы, а изменение пролазов и параметров сета будет заблокировано до повторного открытия.", button: "Подтвердить сет", danger: false }
    : state.action === "reopen"
      ? { title: `Открыть «${state.item.name}»?`, text: "Сет снова станет доступен для исправления результатов и редактирования параметров.", button: "Открыть сет", danger: false }
      : { title: `Удалить «${state.item.name}»?`, text: "Пустой сет будет удален без возможности восстановления.", button: "Удалить сет", danger: true };
  return <ConfirmDialog title={content.title} description={content.text} confirmLabel={content.button} busy={saving} danger={content.danger} onCancel={onClose} onConfirm={() => void onConfirm()}>
    <div className="set-action-summary"><span>Дата<strong>{state.item.scheduled_on?.split("-").reverse().join(".") ?? "Не указана"}</strong></span><span>Время<strong>{state.item.time_label}</strong></span><span>Участники<strong>{state.item.participant_count}/{state.item.capacity}</strong></span><span>Пришли<strong>{state.item.checked_in_count}</strong></span></div>
  </ConfirmDialog>;
}
