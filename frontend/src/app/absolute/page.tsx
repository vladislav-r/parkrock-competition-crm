"use client";

import Link from "next/link";
import PublicHeader from "../components/PublicHeader";
import { publicRefreshMs, usePublicRefresh } from "@/lib/public-refresh";
import { Check, ChevronLeft, Clock3, RefreshCw, Trophy } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AbsoluteResults, AbsoluteStage, getAbsoluteResults, getPublicResults } from "@/lib/api";
import SponsorStrip from "../components/SponsorStrip";
import ResultsNavigation from "../components/ResultsNavigation";

const titles: Record<AbsoluteStage, string> = { qualification: "Квалификация", final: "Финал", overall: "Соревнование" };
const points = (value: number | null) => value?.toLocaleString("ru-RU", { maximumFractionDigits: 1 }) ?? "—";

export default function AbsolutePage() {
  const [stage, setStage] = useState<AbsoluteStage>("qualification");
  const [data, setData] = useState<AbsoluteResults | null>(null);
  const [error, setError] = useState("");
  const [groups, setGroups] = useState<string[]>([]);
  const [refresh, setRefresh] = useState<Parameters<typeof publicRefreshMs>[0]>(null);
  const load = useCallback(async () => {
    try { const [absolute, results] = await Promise.all([getAbsoluteResults(stage), getPublicResults()]); setData(absolute); setGroups(results.groups); setRefresh(results); setError(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось загрузить абсолют"); }
  }, [stage]);
  usePublicRefresh(load, publicRefreshMs(refresh, stage));
  const rows = data?.stage === stage ? data.results : [];
  return <main className="public-page qualification-page sand-theme sand-secondary">
    <div className="sand-frame"><PublicHeader />
    <section className="results-shell qualification-shell"><ResultsNavigation groups={groups} active="absolute"/>
      <div className="qualification-heading"><div><div className="eyebrow">Боулдеринг · {stage === "overall" ? "общий зачёт" : stage === "final" ? "этап 2 из 2" : "этап 1 из 2"}</div><h2>Абсолют</h2><p><span className={`qualification-badge${stage === "final" ? " final" : ""}`}>{stage === "qualification" ? <Check size={14}/> : <Trophy size={14}/>} {titles[stage]}</span>{rows.length} участников · {rows.filter(row => row.has_result).length} с результатом</p></div><button className="icon-button" onClick={() => void load()} title="Обновить"><RefreshCw size={18}/></button></div>
      <nav className="stage-view-tabs" aria-label="Этап абсолюта">{(Object.keys(titles) as AbsoluteStage[]).map((key) => <button key={key} className={stage === key ? `active${key === "final" ? " final" : ""}` : ""} onClick={() => setStage(key)}>{titles[key]}</button>)}</nav>
      {error && <div className="error-banner">{error}</div>}
      {data?.stage === stage && !data.available ? <div className="empty-state">{stage === "qualification" ? "Квалификация ещё не начата" : "Результаты появятся после запуска финала"}</div> : <>
        <div className="qualification-table-wrap"><table className="qualification-table compact absolute-results-table"><thead><tr><th>Место</th><th className="start-number-column">Ст. №</th><th>Участник</th><th>Клуб</th><th>Очки</th></tr></thead><tbody>
          {rows.map((row) => <tr key={row.participant_id}><td>{row.place !== null && <strong>{row.place}</strong>}</td><td className="start-number-column"><span className="bib">{row.start_number}</span></td><td className="athlete-name"><strong>{row.full_name}</strong><small className="absolute-group">{row.group_name}</small></td><td className="club" title={row.club}>{row.club}</td><td className="qualification-total"><strong>{points(row.score)}</strong>{stage === "overall" && <small className="absolute-score-parts">Квал.: {points(row.qualification_points)}<br/>Финал: {points(row.final_points ?? 0)}</small>}</td></tr>)}
        </tbody></table>{!rows.length && !error && <div className="empty-state">Результатов пока нет</div>}</div>
      </>}
      <p className="qualification-legend">Общий зачёт всех полов и возрастов. Равные очки — одинаковое место.{stage === "overall" && " Сумма очков квалификации и финала. Без участия в финале — 0 за финал."}{data?.provisional && " Текущие результаты могут измениться."}</p>
    </section></div><footer className="sand-footer"><SponsorStrip /></footer>
  </main>;
}
