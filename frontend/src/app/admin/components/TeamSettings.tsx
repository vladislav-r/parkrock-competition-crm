"use client";

import { useEffect, useState } from "react";
import { ExternalLink, Medal, Users, Calculator } from "lucide-react";
import { EventInfo, getTeamSettings, TeamSettingsInfo, updateTeamSettings } from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";
import "./team-settings.css";

export function TeamSettings({ event, token, onSaved }: { event: EventInfo; token: string; onSaved: () => Promise<void> }) {
  const [info, setInfo] = useState<TeamSettingsInfo | null>(null);
  const [draft, setDraft] = useState<{ team_quota: number; expected_version: number } | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const values = draft ?? { team_quota: event.team_quota, expected_version: event.version };
  useEffect(() => {
    let active = true;
    getTeamSettings(token).then(data => { if (active) setInfo(data); }).catch(error => { if (active) setMessage(error.message); });
    return () => { active = false; };
  }, [token, event.version]);
  async function save() {
    setSaving(true); setMessage("");
    try { await updateTeamSettings(token, values); setDraft(null); setConfirm(false); await onSaved(); setMessage("Квота сохранена. Оба командных зачёта используют новые настройки."); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Не удалось сохранить настройки"); setConfirm(false); }
    finally { setSaving(false); }
  }
  return <div className="team-settings-grid">
    <form className="settings-card" onSubmit={e => { e.preventDefault(); setConfirm(true); }}>
      <div className="settings-card-head"><div><h2><Users size={22}/> Настройки командного зачёта</h2></div></div>
      <label className="team-quota-label">Участников клуба в каждой группе<input type="number" min={1} max={1000} step={1} required disabled={saving} value={Number.isNaN(values.team_quota) ? "" : values.team_quota} onChange={e => setDraft({ ...values, team_quota: e.target.valueAsNumber })}/></label>
      <button className="primary-action" disabled={saving || !draft}>Сохранить настройки</button>
      {draft && draft.expected_version !== event.version && <p role="status">Настройки изменились. <button type="button" className="secondary-action" onClick={() => setDraft(null)}>Загрузить актуальные</button></p>}
      {message && <p role="status">{message}</p>}
    </form>
    <section className="settings-card">
      <div className="settings-card-head"><div><h2><Medal size={22}/> Готовность результатов</h2></div></div>
      <div className="team-stage-status">{info?.stages.map(stage => <article key={stage.stage}><strong>{stage.stage === "qualification" ? "Квалификация" : "Финал"}</strong><p>{stage.available ? `Итоги доступны · клубов: ${stage.results.length}` : stage.reason}</p>{stage.issues.map(issue => <p className="error-banner" key={issue}>{issue}</p>)}</article>) ?? <p>Проверяем готовность результатов…</p>}</div>
      <a className="secondary-button" href="/teams" target="_blank" rel="noreferrer">Открыть командный зачёт <ExternalLink size={15}/></a>
    </section>
    <section className="settings-card team-rules-card">
      <div className="settings-card-head"><div><h2><Calculator size={22}/> Как считается командный зачёт</h2></div></div>
      <p>Квалификация и финал — два независимых зачёта. Каждый доступен после подтверждения всех категорий своего этапа.</p>
      <p>Квота выше задаёт максимальное количество участников клуба в каждой возрастной группе. Она одинакова для всех групп, квалификации и финала.</p>
      <p>Личное место → баллы ФСР → лучшие участники клуба в группе → сумма всех групп. Если участников меньше квоты, учитываем имеющихся. Равные баллы не расширяют квоту.</p>
      <h3>Баллы ФСР за личные места</h3>
      <div className="team-points-grid">{info?.points.map((points, i) => <div key={i}><span>{i + 1} место</span><strong>{points}</strong></div>)}</div>
      <p className="export-settings-preview">При равных личных местах усредняются баллы занятых позиций. Равные суммы клубов дают места 1, 1, 3. Баллы сравниваются без промежуточного округления; таблица ФСР не редактируется.</p>
      <details><summary>Равенство на границе первых 30 мест</summary><p>Если ниже границы больше половины позиций — 0 баллов; если меньше — среднее с нулями. Случай ровно половины требует официального разъяснения: при его возникновении итоговый расчёт и выгрузка приостанавливаются, здесь появляется объяснение.</p></details>
      <h3>Официальные документы ФСР</h3><div className="team-source-links">{info?.sources.map(source => <a key={source.url} href={source.url} target="_blank" rel="noreferrer">{source.title}<ExternalLink size={16}/></a>)}</div>
    </section>
    {confirm && <ConfirmDialog title="Изменить квоту командного зачёта?" description={`В каждой группе будут учитываться до ${values.team_quota} участников каждого клуба. Доступные итоги квалификации и финала пересчитаются, в том числе после завершения соревнования.`} confirmLabel="Сохранить и пересчитать" busy={saving} onCancel={() => { if (!saving) setConfirm(false); }} onConfirm={() => void save()}/>}
  </div>;
}
