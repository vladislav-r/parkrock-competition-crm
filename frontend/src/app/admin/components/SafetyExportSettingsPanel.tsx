"use client";
import { useEffect, useState } from "react";
import { getSafetyExportSettings, updateSafetyExportSettings, type SafetyExportSettings } from "@/lib/api";

export function SafetyExportSettingsPanel({ token, onSaved }: { token: string; onSaved: (version: number) => void }) {
  const [draft, setDraft] = useState<SafetyExportSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  useEffect(() => { getSafetyExportSettings(token).then(setDraft).catch(e => setMessage(e.message)); }, [token]);
  async function save(event: React.FormEvent) {
    event.preventDefault(); if (!draft || busy) return; setBusy(true); setMessage("");
    try { const next = await updateSafetyExportSettings(token, draft); setDraft(next); onSaved(next.event_version); setMessage("Настройки ТБ сохранены"); }
    catch (e) { setMessage(e instanceof Error ? e.message : "Не удалось сохранить настройки"); }
    finally { setBusy(false); }
  }
  return <form className="settings-card" onSubmit={save}>
    <div className="settings-card-head"><div><h2>Журнал инструктажа по ТБ</h2><p>Реквизиты для Excel и печати. Настройки протоколов не изменяются.</p></div></div>
    {draft && <><div className="export-settings-grid">{([
      ["competition_name", "Полное название фестиваля", 255], ["location", "Город проведения", 255],
      ["dates", "Даты проведения", 255], ["briefing_date", "Дата проведения инструктажа", 100],
      ["official_name", "Заместитель главного судьи по безопасности — ФИО", 200],
    ] as const).map(([key, label, max]) => <label key={key}>{label}<input value={draft[key]} maxLength={max} required={["competition_name", "location", "dates"].includes(key)} onChange={e => setDraft({ ...draft, [key]: e.target.value })}/></label>)}</div>
    <p>Если дата инструктажа или ФИО ответственного не заполнены, в документе останутся строки для заполнения от руки.</p>
    <button className="primary-action" disabled={busy}>{busy ? "Сохраняем…" : "Сохранить настройки ТБ"}</button></>}
    {message && <p role="status">{message}</p>}
  </form>;
}
