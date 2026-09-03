"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, Clock3 } from "lucide-react";
import { getPublicResults, PublicResults } from "@/lib/api";

function occupancyStatus(participants: number, capacity: number) {
  if (participants > capacity) return { label: "Переполнен", tone: "overflow" };
  if (participants >= capacity) return { label: "Заполнен", tone: "full" };
  if (participants / capacity >= 0.8) return { label: "Почти заполнен", tone: "busy" };
  return { label: "Есть места", tone: "available" };
}

export default function SetsPage() {
  const [data, setData] = useState<PublicResults | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setData(await getPublicResults());
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Не удалось загрузить сеты");
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, [load]);

  const totals = useMemo(() => {
    const capacity = data?.sets.reduce((sum, item) => sum + item.capacity, 0) ?? 0;
    const participants = data?.sets.reduce((sum, item) => sum + item.participant_count, 0) ?? 0;
    return { capacity, participants, available: Math.max(0, capacity - participants) };
  }, [data]);

  return <main className="sets-page public-page">
    <header className="public-header">
      <img className="brand-logo public-brand-logo" src="/brand/parkrock-white.svg" alt="ПаркРок"/>
      <div><div className="eyebrow">ПаркРок: Каменный век</div><h1>Загруженность сетов</h1></div>
      <div className="public-nav"><span className="public-header-status"><Clock3 size={14}/>Обновляется автоматически</span><Link className="admin-link" href="/"><ArrowLeft size={16}/>Результаты</Link></div>
    </header>

    <section className="sets-board">
      <div className="sets-summary">
        <div><small>Всего мест</small><strong>{totals.capacity}</strong></div>
        <div><small>Назначено участников</small><strong>{totals.participants}</strong></div>
        <div><small>Свободно мест</small><strong>{totals.available}</strong></div>
      </div>
      {error && <div className="error-banner">{error}</div>}
      <div className="sets-table-wrap">
        <table className="sets-table">
          <thead><tr><th>Сет</th><th>Время</th><th>Занято</th><th>Свободно</th><th>Загрузка</th><th>Статус</th></tr></thead>
          <tbody>{data?.sets.map((item) => {
            const available = Math.max(0, item.capacity - item.participant_count);
            const percent = Math.min(100, Math.round(item.participant_count / item.capacity * 100));
            const status = occupancyStatus(item.participant_count, item.capacity);
            return <tr key={item.id}>
              <td><strong>{item.name}</strong><small>{item.checked_in_count} прибыли</small></td>
              <td>{item.time_label}</td>
              <td><strong>{item.participant_count} из {item.capacity}</strong></td>
              <td><strong>{available}</strong> мест</td>
              <td><div className="set-load"><span><i className={status.tone} style={{ width: `${percent}%` }}/></span><strong>{percent}%</strong></div></td>
              <td><span className={`set-status ${status.tone}`}>{status.label}</span></td>
            </tr>;
          })}</tbody>
        </table>
        {!data?.sets.length && !error && <div className="empty-state">Загружаем список сетов...</div>}
      </div>
    </section>
  </main>;
}
