"use client";

import { useCallback, useEffect, useState } from "react";
import { Archive, Check, CheckCircle2, CircleAlert, Download, Eye, Flag, LayoutDashboard, LockKeyhole, Pencil, RotateCcw, Route, Save, Trophy, X } from "lucide-react";
import { cancelFinalDevelopment, completeFestival, confirmQualificationCategory, downloadQualificationSnapshotCsv, FinalCategoryResults, FinalSetup, FinalStatus, getFinalCategoryResults, getFinalSetup, getFinalStatus, getQualificationCategoryResults, QualificationCategoryReview, reopenQualificationCategory, startFinal, updateFinalCategoryRoutes, updateFinalParticipantResults } from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";

type Category = FinalStatus["categories"][number];
type FinalCategory = FinalSetup["categories"][number];
type FinalRoute = FinalSetup["routes"][number];
type FinalRow = FinalCategoryResults["results"][number];
type FinalView = "overview" | "routes" | "snapshots" | "exports";
type PendingAction =
  | { type: "confirm"; category: Category } | { type: "reopen"; category: Category }
  | { type: "start" } | { type: "cancel" } | { type: "complete" }
  | { type: "routes"; category: FinalCategory; routeIds: string[] }
  | { type: "result"; categoryId: string; row: FinalRow; attempts: Array<{ route_id: string; zone_attempt: number | null; top_attempt: number | null }> };

const sameRoutes = (left: string[], right: string[]) => left.length === right.length && left.every((item) => right.includes(item));
const numberOrNull = (value: string) => { const number = Number(value); return value.trim() && Number.isInteger(number) && number > 0 ? number : null; };

export function FinalSection({ token, onUpdated }: { token: string; onUpdated: () => Promise<void> }) {
  const [status, setStatus] = useState<FinalStatus | null>(null);
  const [setup, setSetup] = useState<FinalSetup | null>(null);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reviewCategory, setReviewCategory] = useState<Category | null>(null);
  const [review, setReview] = useState<QualificationCategoryReview | null>(null);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [routeDrafts, setRouteDrafts] = useState<Record<string, string[]>>({});
  const [editingRouteCategories, setEditingRouteCategories] = useState<Set<string>>(new Set());
  const [finalView, setFinalView] = useState<FinalView>("overview");
  const [finalCategoryResults, setFinalCategoryResults] = useState<Record<string, FinalCategoryResults>>({});
  const [finalResults, setFinalResults] = useState<FinalCategoryResults | null>(null);
  const [finalEditor, setFinalEditor] = useState<FinalRow | null>(null);
  const [attemptDraft, setAttemptDraft] = useState<Record<string, { zone: string; top: string }>>({});
  const load = useCallback(async () => {
    try { setStatus(await getFinalStatus(token)); setError(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось загрузить этап соревнования"); }
  }, [token]);

  useEffect(() => { void load(); const interval = window.setInterval(() => void load(), 3000); return () => window.clearInterval(interval); }, [load]);
  useEffect(() => {
    if (!status || status.stage === "qualification") { setSetup(null); setFinalView("overview"); return; }
    void getFinalSetup(token).then(setSetup).catch((reason) => setError(reason instanceof Error ? reason.message : "Не удалось загрузить настройку финала"));
  }, [status?.stage, token]);
  useEffect(() => {
    if (!setup || status?.stage === "qualification") { setFinalCategoryResults({}); return; }
    let cancelled = false;
    const refresh = () => void Promise.all(setup.categories.map(async (category) => {
      try { return [category.id, await getFinalCategoryResults(token, category.id)] as const; }
      catch { return null; }
    })).then((items) => {
      if (cancelled) return;
      const results: Record<string, FinalCategoryResults> = {};
      for (const item of items) if (item) results[item[0]] = item[1];
      setFinalCategoryResults(results);
    });
    refresh();
    const interval = window.setInterval(refresh, 3000);
    return () => { cancelled = true; window.clearInterval(interval); };
  }, [setup, status?.stage, token]);
  useEffect(() => {
    if (!finalResults || finalEditor) return;
    const refresh = () => void getFinalCategoryResults(token, finalResults.category_id).then((result) => {
      setFinalResults(result);
      setFinalCategoryResults((rows) => ({ ...rows, [result.category_id]: result }));
    }).catch(() => undefined);
    const interval = window.setInterval(refresh, 3000);
    return () => window.clearInterval(interval);
  }, [finalResults?.category_id, finalEditor, token]);

  async function applyAction() {
    if (!pending || !status) return;
    setBusy(true);
    try {
      if (pending.type === "routes") {
        if (!setup) return;
        setSetup(await updateFinalCategoryRoutes(token, pending.category.id, pending.routeIds, setup.event_version));
        setRouteDrafts((drafts) => ({ ...drafts, [pending.category.id]: pending.routeIds }));
        setEditingRouteCategories((categories) => {
          const next = new Set(categories);
          next.delete(pending.category.id);
          return next;
        });
      } else if (pending.type === "result") {
        const updatedResults = await updateFinalParticipantResults(token, pending.categoryId, pending.row.participant_id, pending.row.version, pending.attempts);
        setFinalResults(updatedResults);
        setFinalCategoryResults((results) => ({ ...results, [updatedResults.category_id]: updatedResults }));
        setFinalEditor(null);
      } else {
        const next = pending.type === "confirm" ? await confirmQualificationCategory(token, pending.category.id, pending.category.expected_version)
          : pending.type === "reopen" ? await reopenQualificationCategory(token, pending.category.id, pending.category.expected_version)
          : pending.type === "start" ? await startFinal(token, status.event_version)
          : pending.type === "cancel" ? await cancelFinalDevelopment(token, status.event_version) : await completeFestival(token, status.event_version);
        setStatus(next); setReviewCategory(null); setReview(null); await onUpdated();
      }
      setError(""); setPending(null);
    } catch (reason) { setPending(null); setError(reason instanceof Error ? reason.message : "Действие не выполнено"); await load(); }
    finally { setBusy(false); }
  }

  async function openReview(category: Category) {
    setReviewCategory(category); setReview(null); setReviewLoading(true); setError("");
    try { setReview(await getQualificationCategoryResults(token, category.id)); }
    catch (reason) { setReviewCategory(null); setError(reason instanceof Error ? reason.message : "Не удалось загрузить результаты категории"); }
    finally { setReviewLoading(false); }
  }
  async function openFinalResults(category: FinalCategory) {
    setFinalResults(null); setFinalEditor(null); setError("");
    try { setFinalResults(await getFinalCategoryResults(token, category.id)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось загрузить таблицу финала"); }
  }
  function startResultEdit(row: FinalRow) {
    setFinalEditor(row);
    setAttemptDraft(Object.fromEntries(row.attempts.map((item) => [item.route_id, { zone: item.zone_attempt?.toString() ?? "", top: item.top_attempt?.toString() ?? "" }])));
  }
  async function exportReview() {
    if (!reviewCategory) return;
    try { await downloadQualificationSnapshotCsv(token, reviewCategory.id, reviewCategory.name); setError(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось подготовить выгрузку"); }
  }

  if (!status) return <section className="final-pane"><div className="final-loading">Загрузка состояния квалификации…</div>{error && <div className="error-banner">{error}</div>}</section>;
  const confirmedCount = status.categories.filter((item) => item.confirmed).length;
  const podiums = setup?.categories.filter((category) => category.participates).map((category) => ({
    category,
    rows: (finalCategoryResults[category.id]?.results ?? []).filter((row) => row.place !== null && row.place <= 3 && row.score > 0),
  })).filter((item) => item.rows.length > 0) ?? [];
  const actionCopy = pending?.type === "confirm" ? { title: `Подтвердить «${pending.category.name}»?`, description: "Текущие места и список финалистов категории будут отмечены как проверенные.", label: "Подтвердить результаты", danger: false }
    : pending?.type === "reopen" ? { title: `Снять подтверждение «${pending.category.name}»?`, description: "Категорию потребуется проверить и подтвердить повторно перед запуском финала.", label: "Снять подтверждение", danger: false }
    : pending?.type === "start" ? { title: "Запустить финал?", description: "Квалификация будет заблокирована. Система создаст неизменяемый снимок результатов, финалистов и порядка выхода.", label: "Запустить финал", danger: true }
    : pending?.type === "cancel" ? { title: "Отменить этап «Финал»?", description: "Временный снимок квалификации и результаты финала будут удалены, а редактирование квалификации снова станет доступно.", label: "Вернуть квалификацию", danger: true }
    : pending?.type === "complete" ? { title: "Завершить фестиваль?", description: "Состояние мероприятия изменится на «Завершено». Дальнейшая работа финала будет закрыта.", label: "Завершить фестиваль", danger: true }
    : pending?.type === "routes" ? { title: `Сохранить трассы для «${pending.category.name}»?`, description: "Для категории будут назначены выбранные четыре финальные трассы.", label: "Сохранить трассы", danger: false }
    : { title: `Сохранить результат №${pending?.row.start_number}?`, description: "Финальные баллы и места категории будут пересчитаны. Изменение попадёт в журнал действий.", label: "Сохранить результат", danger: false };

  return <section className="final-workspace">
    <header className="admin-section-hero"><div><div className="eyebrow">Этап соревнования</div><h1>{status.stage === "qualification" ? "Завершение квалификации" : status.stage === "final" ? "Финал запущен" : "Фестиваль завершён"}</h1><p>{status.stage === "qualification" ? "Проверьте каждую категорию. После запуска финала результаты и настройки квалификации изменить нельзя." : status.stage === "final" ? "Сначала назначьте финальные трассы категориям, затем вносите результаты." : "Итоговое состояние фестиваля зафиксировано."}</p></div><div className={`section-health ${status.stage}`}><Trophy size={22}/><span><strong>{status.stage === "qualification" ? `${confirmedCount}/${status.categories.length}` : status.snapshot_finalists}</strong><small>{status.stage === "qualification" ? "категорий подтверждено" : "финалистов"}</small></span></div></header>
    <div className="final-content-grid">
    <aside className="final-sidebar">
      <span className="eyebrow">Финал</span>
      <button className={finalView === "overview" ? "active" : ""} onClick={() => setFinalView("overview")}><LayoutDashboard size={17}/>Главное</button>
      <button disabled={status.stage === "qualification"} className={finalView === "routes" ? "active" : ""} onClick={() => setFinalView("routes")}><Route size={17}/>Результаты</button>
      <button disabled={status.stage === "qualification"} className={finalView === "snapshots" ? "active" : ""} onClick={() => setFinalView("snapshots")}><Archive size={17}/>Снимки квалификации</button>
      <button disabled={status.stage === "qualification"} className={finalView === "exports" ? "active" : ""} onClick={() => setFinalView("exports")}><Download size={17}/>Выгрузка</button>
    </aside>
    <div className="final-pane">
      {error && <div className="error-banner compact">{error}</div>}
      {status.stage === "qualification" && <><div className="final-progress"><span><strong>{confirmedCount}/{status.categories.length}</strong><small>категорий подтверждено</small></span><div><i style={{ width: `${status.categories.length ? confirmedCount / status.categories.length * 100 : 0}%` }}/></div></div><div className="qualification-category-list">{status.categories.map((category) => <article key={category.id} className={category.confirmed ? "qualification-category confirmed" : "qualification-category"}><span className="qualification-status-icon">{category.confirmed ? <CheckCircle2 size={21}/> : <CircleAlert size={21}/>}</span><div><strong>{category.name}</strong><small>{category.result_count} результатов · {category.participates_in_final ? `${category.finalist_count} финалистов` : "без финала · финишеры по медалям"}</small></div><span className="qualification-category-actions"><button className="secondary-button compact-action" onClick={() => void openReview(category)}><Eye size={14}/>Просмотреть</button>{category.confirmed ? <button className="secondary-button compact-action" onClick={() => setPending({ type: "reopen", category })}><RotateCcw size={14}/>Снять</button> : <button className="confirm-results-button" onClick={() => setPending({ type: "confirm", category })}><Check size={15}/>Подтвердить</button>}</span></article>)}</div><div className="final-start-card"><span><LockKeyhole size={23}/><span><strong>Неизменяемый снимок квалификации</strong><small>{status.all_categories_confirmed ? "Все категории проверены. Финал можно запускать." : "Кнопка станет доступна после подтверждения всех категорий, включая категории без финала."}</small></span></span><button className="primary-action" disabled={!status.all_categories_confirmed} onClick={() => setPending({ type: "start" })}><Flag size={17}/>Запустить финал</button></div></>}
      {status.stage !== "qualification" && finalView === "overview" && <><div className="final-snapshot-card"><div><span><strong>{status.snapshot_results}</strong><small>результатов зафиксировано</small></span><span><strong>{status.snapshot_finalists}</strong><small>финалистов</small></span><span><strong>{status.categories.length}</strong><small>категорий</small></span></div>{status.stage === "final" && <div className="final-stage-actions"><button className="danger-outline-button" onClick={() => setPending({ type: "cancel" })}><RotateCcw size={16}/>Отменить финал (разработка)</button><button className="primary-action" onClick={() => setPending({ type: "complete" })}><CheckCircle2 size={16}/>Завершить фестиваль</button></div>}</div><section className="final-podiums"><div className="final-panel-heading"><div><span className="eyebrow">Итоги финала</span><h2>Победители и призёры</h2></div><Trophy size={22}/></div>{podiums.length ? <div className="final-podium-grid">{podiums.map(({ category, rows }) => <article key={category.id}><div><span>{category.short_name}</span><strong>{category.name}</strong></div>{rows.map((row) => <p key={row.id} className={`final-medal place-${row.place}`}><b>{row.place === 1 ? "1" : row.place === 2 ? "2" : "3"}</b><span>{row.full_name}<small>№{row.start_number} · {row.club}</small></span></p>)}</article>)}</div> : <div className="final-podium-empty">Призёры появятся здесь после внесения результатов финала.</div>}</section></>}
      {status.stage !== "qualification" && finalView === "routes" && <FinalSetupPanel setup={setup} stage={status.stage} routeDrafts={routeDrafts} editingCategories={editingRouteCategories} onRoutesChange={setRouteDrafts} onEdit={(categoryId) => setEditingRouteCategories((categories) => new Set(categories).add(categoryId))} onCancelEdit={(category) => { setRouteDrafts((drafts) => ({ ...drafts, [category.id]: category.route_ids })); setEditingRouteCategories((categories) => { const next = new Set(categories); next.delete(category.id); return next; }); }} onSave={(category, routeIds) => setPending({ type: "routes", category, routeIds })} onOpenResults={openFinalResults}/>} 
      {status.stage !== "qualification" && finalView === "snapshots" && <section className="snapshot-categories"><div className="final-panel-heading"><div><span className="eyebrow">Неизменяемые данные</span><h2>Снимки квалификации</h2></div><Archive size={22}/></div><div className="qualification-category-list">{status.categories.map((category) => <article key={category.id} className="qualification-category confirmed"><span className="qualification-status-icon"><CheckCircle2 size={21}/></span><div><strong>{category.name}</strong><small>{category.result_count} результатов · {category.participates_in_final ? `${category.finalist_count} финалистов` : "без финала · финишеры по медалям"}</small></div><button className="secondary-button compact-action" onClick={() => void openReview(category)}><Eye size={14}/>Открыть снимок</button></article>)}</div></section>}
      {status.stage !== "qualification" && finalView === "exports" && <section className="final-exports"><div className="final-panel-heading"><div><span className="eyebrow">Подготовка документов</span><h2>Выгрузка результатов</h2><p>Выгрузки по возрастным категориям станут доступны на следующем шаге.</p></div><Download size={22}/></div><div>{setup?.categories.filter((category) => category.participates).map((category) => <button key={category.id} disabled><Download size={16}/><span><strong>{category.name}</strong><small>CSV / XLSX · скоро</small></span></button>)}</div></section>}
      {reviewCategory && <QualificationReview category={reviewCategory} review={review} loading={reviewLoading} stage={status.stage} onClose={() => { setReviewCategory(null); setReview(null); }} onExport={exportReview} onConfirm={() => { const category = reviewCategory; setReviewCategory(null); setReview(null); setPending({ type: "confirm", category }); }}/>} 
      {finalResults && <FinalResultsDialog results={finalResults} editor={finalEditor} attemptDraft={attemptDraft} stage={status.stage} onClose={() => { setFinalResults(null); setFinalEditor(null); }} onEdit={startResultEdit} onDraft={setAttemptDraft} onSave={(row, attempts) => setPending({ type: "result", categoryId: finalResults.category_id, row, attempts })} onCancelEdit={() => setFinalEditor(null)}/>} 
      {pending && <ConfirmDialog title={actionCopy.title} description={actionCopy.description} confirmLabel={actionCopy.label} danger={actionCopy.danger} busy={busy} onCancel={() => setPending(null)} onConfirm={() => void applyAction()}/>} 
    </div>
    </div>
  </section>;
}

function FinalSetupPanel({ setup, stage, routeDrafts, editingCategories, onRoutesChange, onEdit, onCancelEdit, onSave, onOpenResults }: { setup: FinalSetup | null; stage: string; routeDrafts: Record<string, string[]>; editingCategories: Set<string>; onRoutesChange: (value: Record<string, string[]>) => void; onEdit: (categoryId: string) => void; onCancelEdit: (category: FinalCategory) => void; onSave: (category: FinalCategory, routeIds: string[]) => void; onOpenResults: (category: FinalCategory) => void }) {
  if (!setup) return <div className="final-loading">Загружаем настройку финальных трасс…</div>;
  const finalRoutes = setup.routes;
  function changeSelection(category: FinalCategory, selected: string[], route: FinalRoute) {
    const blockStart = route.number === 1 || route.number === 5 ? route.number : null;
    const routeIds = blockStart === null
      ? selected.includes(route.id) ? selected.filter((id) => id !== route.id) : selected.length < 4 ? [...selected, route.id] : selected
      : finalRoutes.filter((item) => item.number >= blockStart && item.number < blockStart + 4).map((item) => item.id);
    onRoutesChange({ ...routeDrafts, [category.id]: routeIds });
  }
  return <section className="final-setup"><div className="final-setup-head"><div><span className="eyebrow">Настройка финала</span><h2>Результаты</h2><p>Здесь показаны только категории с положительным количеством финалистов. Назначьте каждой ровно четыре трассы.</p></div></div><div className="final-route-overview">{setup.routes.map((route) => <article key={route.id}><strong>{route.name}</strong><small>{route.assigned_categories.length ? route.assigned_categories.join(" · ") : "Не назначена"}</small></article>)}</div><div className="final-category-setup-list">{setup.categories.map((category) => {
    const selected = routeDrafts[category.id] ?? category.route_ids; const configured = selected.length === 4; const editing = editingCategories.has(category.id);
    return <article key={category.id} className="final-category-setup"><div className="final-category-title"><span>{category.short_name}</span><div><strong>{category.name}</strong><small>{category.finalist_count} финалистов</small></div></div><div className="final-route-choice">{setup.routes.map((route) => <button key={route.id} title={route.number === 1 ? "Выбрать трассы 1–4" : route.number === 5 ? "Выбрать трассы 5–8" : undefined} disabled={stage !== "final" || (configured && !editing)} className={selected.includes(route.id) ? "active" : ""} onClick={() => changeSelection(category, selected, route)}>{route.number}</button>)}</div><div className="final-category-actions"><small className={configured ? "ready" : ""}>{configured ? "Назначены 4 трассы" : `Выбрано ${selected.length}/4`}</small>{stage === "final" && configured && !editing && <button className="secondary-button compact-action" onClick={() => onEdit(category.id)}><Pencil size={14}/>Изменить</button>}{stage === "final" && editing && <button className="secondary-button compact-action" onClick={() => onCancelEdit(category)}><X size={14}/>Отмена</button>}{stage === "final" && !sameRoutes(selected, category.route_ids) && <button className="secondary-button compact-action" disabled={!configured} onClick={() => onSave(category, selected)}><Save size={14}/>Сохранить</button>}{configured && <button className="confirm-results-button" onClick={() => onOpenResults(category)}><Trophy size={14}/>Таблица финала</button>}</div></article>;
  })}</div></section>;
}

function QualificationReview({ category, review, loading, stage, onClose, onExport, onConfirm }: { category: Category; review: QualificationCategoryReview | null; loading: boolean; stage: string; onClose: () => void; onExport: () => void; onConfirm: () => void }) {
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><section className="qualification-review-dialog" role="dialog" aria-modal="true" aria-labelledby="qualification-review-title" onMouseDown={(event) => event.stopPropagation()}><button className="dialog-close" onClick={onClose} title="Закрыть"><X size={18}/></button><div className="dialog-icon"><Trophy size={22}/></div><div className="eyebrow">{stage === "qualification" ? "Проверка квалификации" : "Неизменяемый снимок квалификации"}</div><h2 id="qualification-review-title">{category.name}</h2>{loading && <div className="final-loading">Загружаем результаты…</div>}{review && <><div className="qualification-review-summary"><span><strong>{review.results.length}</strong><small>с результатом</small></span><span><strong>{category.participates_in_final ? review.results.filter((item) => item.is_finalist).length : "—"}</strong><small>{category.participates_in_final ? "проходят в финал" : "категория без финала"}</small></span></div><div className="qualification-review-table-wrap"><table className="qualification-review-table"><thead><tr><th>Место</th><th>Выход</th><th>№</th><th>Участник</th><th>Клуб</th><th>Трассы</th><th>Очки</th><th>Статус</th></tr></thead><tbody>{review.results.map((item) => <tr key={item.participant_id} className={item.is_finalist ? "review-finalist" : ""}><td><strong>{item.place}</strong></td><td>{item.exit_order ?? "—"}</td><td>{item.start_number}</td><td>{item.full_name}</td><td>{item.club}</td><td>{item.completed_count}</td><td><strong>{item.points}</strong></td><td>{item.is_finalist ? <span className="review-finalist-badge"><Trophy size={13}/>Финалист</span> : "—"}</td></tr>)}</tbody></table>{review.results.length === 0 && <div className="qualification-review-empty">В категории пока нет участников с результатом.</div>}</div><div className="dialog-actions"><button className="secondary-button" onClick={onClose}>Закрыть</button>{stage !== "qualification" && <button className="secondary-button" onClick={onExport}><Download size={15}/>Выгрузить CSV</button>}{stage === "qualification" && !category.confirmed && <button className="confirm-results-button" onClick={onConfirm}><Check size={15}/>Подтвердить результаты</button>}</div></>}</section></div>;
}

function FinalResultsDialog({ results, editor, attemptDraft, stage, onClose, onEdit, onDraft, onSave, onCancelEdit }: { results: FinalCategoryResults; editor: FinalRow | null; attemptDraft: Record<string, { zone: string; top: string }>; stage: string; onClose: () => void; onEdit: (row: FinalRow) => void; onDraft: (draft: Record<string, { zone: string; top: string }>) => void; onSave: (row: FinalRow, attempts: Array<{ route_id: string; zone_attempt: number | null; top_attempt: number | null }>) => void; onCancelEdit: () => void }) {
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><section className="final-results-dialog" role="dialog" aria-modal="true" aria-labelledby="final-results-title" onMouseDown={(event) => event.stopPropagation()}><button className="dialog-close" onClick={onClose} title="Закрыть"><X size={18}/></button><div className="dialog-icon"><Trophy size={22}/></div><div className="eyebrow">Общая таблица финала</div><h2 id="final-results-title">{results.category_name}</h2><div className="final-results-table-wrap"><table className="final-results-table"><thead><tr><th>Место</th><th>№</th><th>Участник</th><th>Квал.</th><th>Выход</th>{results.routes.map((route) => <th key={route.id}>{route.name}</th>)}<th>Топы</th><th>Зоны</th><th>Баллы</th><th/></tr></thead><tbody>{results.results.map((row) => <tr key={row.id}><td><strong>{row.place ?? "—"}</strong></td><td>{row.start_number}</td><td>{row.full_name}<small>{row.club}</small></td><td>{row.qualification_place}</td><td>{row.exit_order ?? "—"}</td>{row.attempts.map((attempt) => <td key={attempt.route_id}>{attempt.top_attempt ? <><strong className="attempt-kind">Т</strong> {attempt.top_attempt}</> : attempt.zone_attempt ? <><strong className="attempt-kind">З</strong> {attempt.zone_attempt}</> : "—"}<small>{attempt.score}</small></td>)}<td>{row.top_count} / {row.top_attempts || "—"}</td><td>{row.zone_count} / {row.zone_attempts || "—"}</td><td><strong>{row.score}</strong></td><td>{stage === "final" && <button className="icon-button" title="Изменить результат" onClick={() => onEdit(row)}><Pencil size={15}/></button>}</td></tr>)}</tbody></table>{results.results.length === 0 && <div className="qualification-review-empty">В этой категории нет финалистов.</div>}</div>{editor && <div className="final-result-editor"><div><strong>Результат №{editor.start_number} · {editor.full_name}</strong><small>Укажите попытку зоны и топа. Если есть топ, в баллах учитывается только его попытка.</small></div><div className="final-attempt-fields">{editor.attempts.map((attempt) => <label key={attempt.route_id}><strong>{attempt.route_name}</strong><span>Зона<input type="number" min="1" value={attemptDraft[attempt.route_id]?.zone ?? ""} onChange={(event) => onDraft({ ...attemptDraft, [attempt.route_id]: { ...attemptDraft[attempt.route_id], zone: event.target.value } })}/></span><span>Топ<input type="number" min="1" value={attemptDraft[attempt.route_id]?.top ?? ""} onChange={(event) => onDraft({ ...attemptDraft, [attempt.route_id]: { ...attemptDraft[attempt.route_id], top: event.target.value } })}/></span></label>)}</div><div className="dialog-actions"><button className="secondary-button" onClick={onCancelEdit}>Отмена</button><button className="confirm-results-button" onClick={() => onSave(editor, editor.attempts.map((attempt) => ({ route_id: attempt.route_id, zone_attempt: numberOrNull(attemptDraft[attempt.route_id]?.zone ?? ""), top_attempt: numberOrNull(attemptDraft[attempt.route_id]?.top ?? "") })))}><Save size={15}/>Проверить и сохранить</button></div></div>}<div className="dialog-actions"><button className="secondary-button" onClick={onClose}>Закрыть</button></div></section></div>;
}
