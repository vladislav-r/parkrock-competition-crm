"use client";

import { useState } from "react";
import { EventInfo, updatePublicRefresh } from "@/lib/api";

export function PublicRefreshSettings({ event, token, onSaved }: { event: EventInfo; token: string; onSaved: () => Promise<void> }) {
  const [draft, setDraft] = useState<{ qualification_refresh_seconds: number; final_refresh_seconds: number; expected_version: number } | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const values = draft ?? { qualification_refresh_seconds: event.qualification_refresh_seconds, final_refresh_seconds: event.final_refresh_seconds, expected_version: event.version };
  return <form onSubmit={async e => {
    e.preventDefault(); setSaving(true); setMessage("");
    try { await updatePublicRefresh(token, values); await onSaved(); setDraft(null); setMessage("Интервалы сохранены"); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Не удалось сохранить интервалы"); }
    finally { setSaving(false); }
  }}>
    <div className="settings-card-head"><div><h2>Автообновление сайта</h2><p>Интервал зависит от открытой вкладки: квалификация или финал. Значения в секундах, от 3 до 300.</p></div></div>
    <div className="export-settings-grid">
      {([['qualification_refresh_seconds', 'Квалификация'], ['final_refresh_seconds', 'Финал']] as const).map(([key, label]) => <label key={key}>{label}, сек.<input type="number" min={3} max={300} step={1} required value={Number.isNaN(values[key]) ? "" : values[key]} disabled={saving} onChange={e => { setDraft({ ...values, [key]: e.target.valueAsNumber }); setMessage(""); }}/></label>)}
    </div>
    <p className="export-settings-preview">Настройки действуют на таблицы категорий, абсолют и ТВ. Главная и сеты используют интервал текущего этапа. Открытые страницы подхватят изменения при следующем обновлении. Частота синхронизации рабочих мест сотрудников не меняется.</p>
    <button className="primary-action export-settings-save" disabled={saving || !draft}>Сохранить интервалы</button>
    {draft && draft.expected_version !== event.version && <button type="button" className="secondary-action" onClick={() => { setDraft(null); setMessage(""); }}>Загрузить актуальные настройки</button>}
    {message && <p className="export-settings-preview" role="status">{message}</p>}
  </form>;
}
