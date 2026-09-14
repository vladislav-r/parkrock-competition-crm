"use client";

import { Fragment, useCallback, useState } from "react";
import { RefreshCw, Trophy } from "lucide-react";
import { getPublicResults, getTeamResults, TeamResults, TeamStage } from "@/lib/api";
import { publicRefreshMs, usePublicRefresh } from "@/lib/public-refresh";
import PublicHeader from "../components/PublicHeader";
import ResultsNavigation from "../components/ResultsNavigation";
import SponsorStrip from "../components/SponsorStrip";
import "./teams.css";

const points = (value: number) => value.toLocaleString("ru-RU", { maximumFractionDigits: 3 });
export default function TeamsPage() {
  const [stage, setStage] = useState<TeamStage>("qualification");
  const [data, setData] = useState<TeamResults | null>(null);
  const [groups, setGroups] = useState<string[]>([]);
  const [refresh, setRefresh] = useState<Parameters<typeof publicRefreshMs>[0]>(null);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const load = useCallback(async () => {
    try { const [teams, publicData] = await Promise.all([getTeamResults(stage), getPublicResults()]); setData(teams); setGroups(publicData.groups); setRefresh(publicData); setError(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось загрузить командный зачёт"); }
  }, [stage]);
  usePublicRefresh(load, publicRefreshMs(refresh, stage));
  const current = data?.stage === stage ? data : null;
  return <main className="public-page qualification-page sand-theme sand-secondary">
    <div className="sand-frame"><PublicHeader/>
    <section className="results-shell qualification-shell">
      <ResultsNavigation groups={groups} active="teams"/>
      <div className="qualification-heading"><div><div className="eyebrow">Боулдеринг · все возрастные группы</div><h2>Командный зачёт</h2><p><span className={`qualification-badge${stage === "final" ? " final" : ""}`}><Trophy size={14}/>{stage === "qualification" ? "Квалификация" : "Финал"}</span>{current && `Квота: ${current.quota} на клуб в каждой группе`}</p></div><button className="icon-button" title="Обновить" onClick={() => void load()}><RefreshCw size={18}/></button></div>
      <nav className="stage-view-tabs" aria-label="Этап командного зачёта">{(["qualification", "final"] as const).map(key => <button key={key} className={stage === key ? `active${key === "final" ? " final" : ""}` : ""} onClick={() => { setStage(key); setExpanded(null); }}>{key === "qualification" ? "Квалификация" : "Финал"}</button>)}</nav>
      {error && <div className="error-banner" role="alert">{error}</div>}
      {!current ? <div className="empty-state">Загружаем командный зачёт…</div> : !current.available ? <div className="empty-state"><Trophy size={30}/><h3>{current.reason}</h3><p>Результаты появятся здесь автоматически.</p>{current.issues.map(issue => <p key={issue}>{issue}</p>)}</div> : <div className="qualification-table-wrap"><table className="qualification-table team-results-table"><thead><tr><th>Место</th><th>Клуб</th><th>Баллы</th></tr></thead><tbody>{current.results.map(team => <Fragment key={team.club_id}>
        <tr><td><strong>{team.place}</strong></td><td><button className="team-expand" aria-expanded={expanded === team.club_id} aria-controls={`team-${team.club_id}`} onClick={() => setExpanded(expanded === team.club_id ? null : team.club_id)}><strong>{team.club}</strong><small>{expanded === team.club_id ? "Скрыть вклад участников ↑" : "Вклад участников ↓"}</small></button></td><td className="qualification-total"><strong title={team.points_exact}>{points(team.points)}</strong></td></tr>
        {expanded === team.club_id && <tr id={`team-${team.club_id}`} className="team-detail-row"><td colSpan={3}><div className="team-group-details">{team.groups.map(group => <section key={group.name}><header><h3>{group.name}</h3><strong>{points(group.points)} баллов</strong></header>{group.members.length ? group.members.map(member => <div className="team-member" key={member.participant_id}><span><strong>{member.full_name}</strong><small>№ {member.start_number} · личное место {member.place}</small></span><strong title={member.points_exact}>{points(member.points)}</strong></div>) : <p>Нет участников с положительным вкладом</p>}</section>)}</div></td></tr>}
      </Fragment>)}</tbody></table>{!current.results.length && <div className="empty-state">Нет результатов участников клубов</div>}</div>}
      <p className="qualification-legend">Баллы ФСР за личные места. Лучшие результаты клуба в каждой группе суммируются в общий итог. Равные суммы — одинаковое место. Отображение до трёх знаков; места определяются по точным суммам.</p>
    </section></div><footer className="sand-footer"><SponsorStrip/></footer>
  </main>;
}
