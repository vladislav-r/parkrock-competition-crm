"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, GripVertical, LockKeyhole } from "lucide-react";
import { FinalSetup, getFinalSetup, moveFinalCategory } from "@/lib/api";
import "./final-streams.css";

type Category = FinalSetup["categories"][number];

export function FinalStreamsPanel({ token, setup, stage, onUpdated, onParticipationChange }: {
  token: string; setup: FinalSetup | null; stage: string;
  onUpdated: (value: FinalSetup) => void;
  onParticipationChange: (category: Category, participates: boolean) => void;
}) {
  const recoveryRequest = useRef<AbortController | null>(null);
  useEffect(() => {
    recoveryRequest.current = new AbortController();
    return () => recoveryRequest.current?.abort();
  }, [stage]);
  const [dragged, setDragged] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  if (!setup) return <div className="final-loading">Загружаем потоки финала…</div>;
  const currentSetup = setup;
  const groups = (stream: number | null) => currentSetup.categories
    .filter(c => c.participates && (c.stream_number ?? null) === stream)
    .sort((a, b) => (a.stream_order ?? 0) - (b.stream_order ?? 0));

  async function move(id: string, stream: number | null, before: string | null = null) {
    if (busy || stage !== "final" || id === before) return;
    const signal = recoveryRequest.current?.signal;
    setBusy(true); setMessage(""); setDragged(null); setDropTarget(null);
    try {
      const updated = await moveFinalCategory(token, id, stream, before, currentSetup.event_version);
      if (signal?.aborted) return;
      onUpdated(updated);
      setMessage("Порядок сохранён. Список судьи обновится автоматически.");
    } catch (reason) {
      if (signal?.aborted) return;
      setMessage(reason instanceof Error ? reason.message : "Не удалось сохранить порядок");
      try { const updated = await getFinalSetup(token, signal); if (!signal?.aborted) onUpdated(updated); } catch { /* Keep last confirmed layout. */ }
    } finally { setBusy(false); }
  }

  function card(category: Category, index: number, list: Category[]) {
    const disabled = busy || stage !== "final" || category.assignment_locked;
    return <article key={category.id} className={`final-stream-card${dropTarget === category.id ? " drop-before" : ""}`}
      data-category-id={category.id} draggable={!disabled}
      onDragStart={event => {
        // ReadOnlyScope disables the select as well as the buttons.
        if (disabled || event.currentTarget.querySelector("select")?.disabled) { event.preventDefault(); return; }
        event.dataTransfer.setData("text/plain", category.id); event.dataTransfer.effectAllowed = "move";
        setDragged(category.id);
      }}
      onDragEnd={() => { setDragged(null); setDropTarget(null); }}
      onDragOver={event => { if (!dragged || dragged === category.id) return; event.preventDefault(); event.stopPropagation(); setDropTarget(category.id); }}
      onDrop={event => { event.preventDefault(); event.stopPropagation(); if (dragged) void move(dragged, category.stream_number ?? null, category.stream_number == null ? null : category.id); }}>
      <div className="final-stream-card-title"><GripVertical size={18} aria-hidden="true"/>
        <span className="final-stream-position">{category.stream_number ? index + 1 : "—"}</span>
        <div><strong>{category.name}</strong><small>{category.finalist_count} финалистов</small></div>
        {category.assignment_locked && <LockKeyhole size={17} aria-label="Есть результаты"/>}
      </div>
      {category.stream_number == null && category.route_ids.length > 0 && <p className="final-stream-legacy">Сохранён прежний набор трасс: {currentSetup.routes.filter(r => category.route_ids.includes(r.id)).map(r => r.number).join(", ")}. {category.assignment_locked ? "Изменение доступно после сброса результатов." : "Выберите поток для переназначения."}</p>}
      <div className="final-stream-card-controls">
        <select aria-label={`Поток: ${category.name}`} disabled={disabled} value={category.stream_number ?? ""}
          onChange={event => void move(category.id, event.target.value ? Number(event.target.value) : null)}>
          <option value="">Без потока</option><option value="1">Поток 1 · 1–4</option><option value="2">Поток 2 · 5–8</option>
        </select>
        {category.stream_number != null && <>
          <button type="button" aria-label={`Выше: ${category.name}`} disabled={disabled || index === 0 || list[index - 1]?.assignment_locked} onClick={() => void move(category.id, category.stream_number, list[index - 1].id)}><ArrowUp size={18}/></button>
          <button type="button" aria-label={`Ниже: ${category.name}`} disabled={disabled || index === list.length - 1 || list[index + 1]?.assignment_locked} onClick={() => void move(category.id, category.stream_number, list[index + 2]?.id ?? null)}><ArrowDown size={18}/></button>
        </>}
      </div>
      {category.assignment_locked && <small>Есть результаты · перенос и порядок заблокированы</small>}
    </article>;
  }

  return <section className="final-setup final-streams">
    <div className="final-setup-head"><div className="final-setup-heading-body"><h2>Потоки и порядок выхода</h2>
      <p>Перетащите категории в поток и расположите сверху вниз в порядке выхода. Внутри категории финалисты идут в установленном порядке. На телефоне используйте выбор потока и стрелки. Перенос на карточку ставит категорию перед ней, в свободную область — в конец потока.</p></div></div>
    <div className="final-stream-feedback" role="status">{busy ? "Сохраняем…" : message}</div>
    <div className="final-stream-columns">
      {([null, 1, 2] as const).map(stream => {
        const list = groups(stream);
        return <section key={stream ?? "unassigned"} className={`final-stream-column${stream === null ? " unassigned" : ""}${dropTarget === `stream-${stream}` ? " drop-active" : ""}`} data-stream={stream ?? "unassigned"}
          onDragOver={event => { if (!dragged) return; event.preventDefault(); setDropTarget(`stream-${stream}`); }}
          onDrop={event => { event.preventDefault(); if (dragged) void move(dragged, stream); }}>
          <header><h3>{stream ? `Поток ${stream}` : "Нераспределённые категории"}</h3><span>{list.length} категорий</span></header>
          {stream && <p className="final-stream-routes">Трассы {stream === 1 ? "1 → 2 → 3 → 4" : "5(1) → 6(2) → 7(3) → 8(4)"}</p>}
          {list.map((category, index) => card(category, index, list))}
          {!list.length && <div className="final-stream-empty">{stream ? "Перетащите сюда категорию" : "Все участвующие категории распределены"}</div>}
        </section>;
      })}
    </div>
    {currentSetup.categories.some(c => c.participation_configurable) && <div className="final-stream-participation">
      <h3>Участие младших групп</h3>
      {currentSetup.categories.filter(c => c.participation_configurable).map(category => <label key={category.id}><span>{category.name}</span>
        <button type="button" role="switch" aria-label={`Участие в финале: ${category.name}`} aria-checked={category.participates}
          disabled={busy || stage !== "final" || (!category.participates && category.finalist_limit <= 0)}
          className={`final-participation-toggle${category.participates ? " active" : ""}`}
          onClick={() => onParticipationChange(category, !category.participates)}><i aria-hidden="true"/>{category.participates ? "Финал включён" : "Финал выключен"}</button>
      </label>)}
    </div>}
  </section>;
}
