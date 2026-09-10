"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { AbsoluteResults, AbsoluteStage, getAbsoluteResults } from "@/lib/api";
import SponsorStrip from "../components/SponsorStrip";

const titles: Record<AbsoluteStage, string> = { qualification: "Квалификация", final: "Финал", overall: "Соревнование" };
const points = (value: number | null) => value?.toLocaleString("ru-RU", { maximumFractionDigits: 1 }) ?? "—";

export default function AbsolutePage() {
  const [stage, setStage] = useState<AbsoluteStage>("qualification");
  const [data, setData] = useState<AbsoluteResults | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try { setData(await getAbsoluteResults(stage)); setError(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось загрузить абсолют"); }
  }, [stage]);
  useEffect(() => { void load(); const timer = window.setInterval(() => void load(), 3000); return () => window.clearInterval(timer); }, [load]);
  const rows = data?.stage === stage ? data.results : [];
  return <main className="public-page qualification-page">
    <header className="public-header"><Link href="/" className="header-back" aria-label="К категориям">←</Link><img className="brand-logo public-brand-logo" src="/brand/parkrock-black.svg" alt="ПаркРок"/><div><div className="eyebrow">Онлайн-результаты</div><h1>Абсолют</h1></div><div className="public-nav"><Link href="/">Категории</Link></div></header>
    <SponsorStrip/>
    <section className="results-shell qualification-shell"><div className="qualification-heading"><div><h2>Абсолют · {titles[stage]}</h2><p>Общий зачёт всех полов и возрастов. Равные очки — одинаковое место.</p>{stage === "overall" && <p>Сумма очков квалификации и финала. Без участия в финале — 0 за финал.</p>}</div></div>
      <nav className="stage-view-tabs" aria-label="Этап абсолюта">{(Object.keys(titles) as AbsoluteStage[]).map((key) => <button key={key} className={stage === key ? "active" : ""} onClick={() => setStage(key)}>{titles[key]}</button>)}</nav>
      {error && <div className="error-banner">{error}</div>}
      {data?.stage === stage && !data.available ? <div className="empty-state">{stage === "qualification" ? "Квалификация ещё не начата" : "Результаты появятся после запуска финала"}</div> : <>
        {data?.provisional && <p className="qualification-legend">Текущие результаты обновляются автоматически и могут измениться.</p>}
        <div className="absolute-table-wrap"><table className="absolute-table"><thead><tr><th>Место</th><th>Участник</th>{stage === "overall" && <><th>Квал.</th><th>Финал</th></>}<th>Очки</th></tr></thead><tbody>
          {rows.map((row) => <tr key={row.participant_id}><td>{row.place ?? "—"}</td><td><strong>{row.full_name}</strong><small>№{row.start_number} · {row.group_name} · {row.club}</small></td>{stage === "overall" && <><td>{points(row.qualification_points)}</td><td>{points(row.final_points ?? 0)}</td></>}<td><strong>{points(row.score)}</strong></td></tr>)}
        </tbody></table></div>{!rows.length && !error && <div className="empty-state">Результатов пока нет</div>}
      </>}
    </section>
  </main>;
}
