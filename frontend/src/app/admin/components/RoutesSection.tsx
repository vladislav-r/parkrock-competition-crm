"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronDown, ChevronUp, CircleAlert, CircleCheck, Plus, Save, Trash2, X } from "lucide-react";
import { ApiError, createRoutes, deleteAllRoutes, deleteRoute, getRouteGradePoints, previewRouteGradePoints, Route, RouteGradePoint, updateRoute, updateRouteGradePoints } from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";

const GRADE_LEVELS = [5, 6, 7, 8] as const;
const GRADE_SUFFIXES = ["A", "A+", "B", "B+", "C", "C+"] as const;
const ROUTE_GRADES = GRADE_LEVELS.flatMap((level) => GRADE_SUFFIXES.map((suffix) => `${level}${suffix}`));
const LEVEL_LABELS: Record<number, string> = { 5: "Пятёрки", 6: "Шестёрки", 7: "Семёрки", 8: "Восьмёрки" };

type GradePreview = { changed_grades: number; affected_routes: number; affected_participants: number };
type PendingChange = { type: "create"; payload: { count: number; grade: string } } | { type: "grade-points"; preview: GradePreview };

export function RoutesSection({ routes, token, onUpdated }: { routes: Route[]; token: string; onUpdated: () => Promise<void> }) {
  const [adding, setAdding] = useState(false);
  const [notification, setNotification] = useState<RouteNotification | null>(null);
  const [sort, setSort] = useState<{ key: RouteSortKey; direction: "asc" | "desc" }>({ key: "number", direction: "asc" });
  const [filters, setFilters] = useState({ number: "", grade: "", minPoints: "", maxPoints: "" });
  const [pendingChange, setPendingChange] = useState<PendingChange | null>(null);
  const [changeSaving, setChangeSaving] = useState(false);
  const [gradePoints, setGradePoints] = useState<RouteGradePoint[]>([]);
  const [gradeDraft, setGradeDraft] = useState<Record<string, string>>({});
  const [routeToDelete, setRouteToDelete] = useState<Route | null>(null);
  const [routeDeleting, setRouteDeleting] = useState(false);
  const [deleteAllOpen, setDeleteAllOpen] = useState(false);
  const [allRoutesDeleting, setAllRoutesDeleting] = useState(false);

  const loadGradePoints = useCallback(async () => {
    try {
      const response = await getRouteGradePoints(token);
      setGradePoints(response.items);
      setGradeDraft(Object.fromEntries(response.items.map((item) => [item.grade, item.points === null ? "" : String(item.points)])));
    } catch (error) {
      setNotification({ type: "error", title: error instanceof Error ? error.message : "Не удалось загрузить очки сложностей" });
    }
  }, [token]);
  useEffect(() => { void loadGradePoints(); }, [loadGradePoints]);

  const visibleRoutes = useMemo(() => routes.filter((route) => {
    if (filters.number && !String(route.number).includes(filters.number.trim())) return false;
    if (filters.grade && route.grade !== filters.grade) return false;
    if (filters.minPoints !== "" && route.points < Number(filters.minPoints)) return false;
    if (filters.maxPoints !== "" && route.points > Number(filters.maxPoints)) return false;
    return true;
  }).sort((left, right) => {
    let result = 0;
    if (sort.key === "number") result = left.number - right.number;
    if (sort.key === "grade") result = ROUTE_GRADES.indexOf(left.grade) - ROUTE_GRADES.indexOf(right.grade);
    if (sort.key === "points") result = left.points - right.points;
    return sort.direction === "asc" ? result : -result;
  }), [routes, filters, sort]);

  const routeGroups = useMemo(() => {
    const groups = new Map<string, Route[]>();
    for (const route of visibleRoutes) {
      const grade = route.grade.replace(/\+$/, "");
      if (!groups.has(grade)) groups.set(grade, []);
      groups.get(grade)!.push(route);
    }
    return [...groups].sort(([left], [right]) => left.localeCompare(right, "en", { numeric: true }));
  }, [visibleRoutes]);

  const gradePayload = gradePoints.map((item) => ({
    grade: item.grade,
    points: gradeDraft[item.grade]?.trim() === "" ? null : Number(gradeDraft[item.grade]),
    expected_version: item.expected_version,
  }));
  const gradeDirty = gradePoints.some((item) => (item.points === null ? "" : String(item.points)) !== (gradeDraft[item.grade] ?? ""));

  function changeSort(key: RouteSortKey) {
    setSort((current) => current.key === key ? { key, direction: current.direction === "asc" ? "desc" : "asc" } : { key, direction: "asc" });
  }
  function changeFilter(key: keyof typeof filters, value: string) { setFilters((current) => ({ ...current, [key]: value })); }
  function showSuccess(title: string) { setNotification({ type: "success", title }); }
  function showError(title: string, error: unknown) { setNotification({ type: "error", title, details: error instanceof Error ? error.message : String(error) }); }
  function requestAddRoute(formData: FormData) { setPendingChange({ type: "create", payload: { count: Number(formData.get("count")), grade: String(formData.get("grade")) } }); }
  async function refreshRoutes() { await Promise.all([onUpdated(), loadGradePoints()]); }
  async function removeRoute() {
    if (!routeToDelete) return;
    setRouteDeleting(true);
    try {
      await deleteRoute(token, routeToDelete.id, routeToDelete.version);
      await refreshRoutes();
      showSuccess(`Трасса №${routeToDelete.number} удалена`);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) await refreshRoutes();
      showError(`Не удалось удалить трассу №${routeToDelete.number}`, error);
    } finally {
      setRouteDeleting(false);
      setRouteToDelete(null);
    }
  }
  async function removeAllRoutes() {
    setAllRoutesDeleting(true);
    try {
      const response = await deleteAllRoutes(token);
      await refreshRoutes();
      showSuccess(`Удалено трасс: ${response.deleted}`);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) await refreshRoutes();
      showError("Не удалось удалить все трассы", error);
    } finally {
      setAllRoutesDeleting(false);
      setDeleteAllOpen(false);
    }
  }

  async function requestGradePoints() {
    setChangeSaving(true);
    try { setPendingChange({ type: "grade-points", preview: await previewRouteGradePoints(token, gradePayload) }); }
    catch (error) { showError("Не удалось проверить справочник очков", error); }
    finally { setChangeSaving(false); }
  }
  async function applyPendingChange() {
    if (!pendingChange) return;
    setChangeSaving(true);
    try {
      if (pendingChange.type === "create") {
        const created = await createRoutes(token, pendingChange.payload.count, pendingChange.payload.grade);
        setAdding(false); await refreshRoutes(); showSuccess(`Добавлено трасс: ${created.length}`);
      } else {
        const response = await updateRouteGradePoints(token, gradePayload);
        setGradePoints(response.items);
        setGradeDraft(Object.fromEntries(response.items.map((item) => [item.grade, item.points === null ? "" : String(item.points)])));
        await onUpdated(); showSuccess("Очки категорий сложности сохранены");
      }
      setPendingChange(null);
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) { await onUpdated(); await loadGradePoints(); }
      showError(pendingChange.type === "create" ? "Не удалось добавить трассу" : "Не удалось сохранить очки сложностей", error);
      setPendingChange(null);
    } finally { setChangeSaving(false); }
  }

  return <section className="routes-config-pane"><div className="admin-workspace-container">
    <header className="config-header admin-section-hero"><div><div className="eyebrow">Конфигурация фестиваля</div><h1>Трассы</h1><p>Показано {visibleRoutes.length} из {routes.length} · активных {routes.filter((route) => route.is_active).length}</p></div><div style={{ display: "flex", gap: 10, flexWrap: "wrap", justifyContent: "flex-end" }}><button className="danger-outline-button" disabled={routes.length === 0} onClick={() => setDeleteAllOpen(true)}><Trash2 size={17}/>Удалить все</button><button className="primary-action" onClick={() => setAdding(true)}><Plus size={17}/>Добавить трассу</button></div></header>
    {notification && <RouteToast notification={notification} onClose={() => setNotification(null)}/>} 
    <section className="grade-points-panel"><div className="grade-points-head"><div><div className="eyebrow">Общий справочник</div><h2>Очки по категориям сложности</h2><p>Пустое значение считается нулём. Очки применяются ко всем трассам выбранной сложности.</p></div><button className="save-route-button" disabled={!gradeDirty || changeSaving || gradePoints.length === 0} onClick={() => void requestGradePoints()}><Save size={16}/>Сохранить очки</button></div><div className="grade-points-groups">{GRADE_LEVELS.map((level) => <article key={level}><strong>{LEVEL_LABELS[level]}</strong><div>{GRADE_SUFFIXES.map((suffix) => { const grade = `${level}${suffix}`; const item = gradePoints.find((row) => row.grade === grade); return <label key={grade}><span>{grade}<small>{item?.route_count ?? 0} трасс</small></span><input type="number" min="0" value={gradeDraft[grade] ?? ""} placeholder="0" aria-label={`Очки ${grade}`} onChange={(event) => setGradeDraft((draft) => ({ ...draft, [grade]: event.target.value }))}/></label>; })}</div></article>)}</div></section>
    {adding && <form action={requestAddRoute} className="new-route-form"><div className="route-number-preview">Новые</div><label>Количество<input type="number" name="count" min="1" max="100" defaultValue="1" required/></label><label>Начальная категория<select name="grade" defaultValue="6A">{ROUTE_GRADES.map((item) => <option key={item}>{item}</option>)}</select></label><button className="save-route-button"><Plus size={17}/>Добавить трассы</button><button type="button" className="secondary-button" onClick={() => setAdding(false)}>Отмена</button></form>}
    <div className="routes-config-browser"><div className="routes-sort-bar"><span>Сортировка внутри блоков</span><RouteSortButton label="Номер" sortKey="number" sort={sort} onSort={changeSort}/><RouteSortButton label="Категория" sortKey="grade" sort={sort} onSort={changeSort}/><RouteSortButton label="Очки" sortKey="points" sort={sort} onSort={changeSort}/></div><div className="routes-filter-row"><input value={filters.number} onChange={(event) => changeFilter("number", event.target.value)} placeholder="№ трассы" aria-label="Фильтр по номеру"/><select value={filters.grade} onChange={(event) => changeFilter("grade", event.target.value)} aria-label="Фильтр по категории"><option value="">Все категории</option>{ROUTE_GRADES.map((item) => <option key={item}>{item}</option>)}</select><div className="points-filter"><input type="number" min="0" value={filters.minPoints} onChange={(event) => changeFilter("minPoints", event.target.value)} placeholder="Очки от" aria-label="Минимум очков"/><input type="number" min="0" value={filters.maxPoints} onChange={(event) => changeFilter("maxPoints", event.target.value)} placeholder="до" aria-label="Максимум очков"/></div><button className="clear-filters" onClick={() => setFilters({ number: "", grade: "", minPoints: "", maxPoints: "" })} title="Сбросить фильтры"><X size={16}/></button></div><div className="route-grade-groups">{routeGroups.map(([grade, items]) => <section className="route-grade-group" key={grade} aria-label={`Трассы ${grade} и ${grade}+`}>
      <h2>{grade} / {grade}+<span>Трасс: {items.length}</span></h2>
      <div className="route-card-grid">{items.map((route) => <RouteEditor key={route.id} route={route} token={token} onUpdated={refreshRoutes} onDeleteRequest={setRouteToDelete} onSuccess={showSuccess} onError={showError}/>)}</div>
    </section>)}</div>{visibleRoutes.length === 0 && <div className="routes-empty">Трассы по выбранным фильтрам не найдены</div>}</div>
    {pendingChange && <ConfirmDialog title={pendingChange.type === "create" ? `Добавить трассы: ${pendingChange.payload.count}?` : "Сохранить общий справочник очков?"} description={pendingChange.type === "create" ? `Будет создано ${pendingChange.payload.count} трасс подряд с категорией ${pendingChange.payload.grade}. Номера назначатся автоматически.` : `Изменится категорий: ${pendingChange.preview.changed_grades}. Будет пересчитано трасс: ${pendingChange.preview.affected_routes}, участников: ${pendingChange.preview.affected_participants}.`} confirmLabel={pendingChange.type === "create" ? "Добавить трассы" : "Применить пересчёт"} busy={changeSaving} onCancel={() => setPendingChange(null)} onConfirm={() => void applyPendingChange()}/>} 
    {routeToDelete && <ConfirmDialog title={`Удалить трассу №${routeToDelete.number}?`} description="Удаление возможно только если по трассе ещё нет сохранённых прохождений и она не назначена судье." confirmLabel="Удалить трассу" busy={routeDeleting} danger onCancel={() => setRouteToDelete(null)} onConfirm={() => void removeRoute()}/>} 
    {deleteAllOpen && <ConfirmDialog title="Удалить все трассы?" description={`Будут безвозвратно удалены все ${routes.length} квалификационных трасс. Операция недоступна, если по любой трассе есть сохранённое прохождение или назначен судья.`} confirmLabel="Удалить все трассы" busy={allRoutesDeleting} danger onCancel={() => setDeleteAllOpen(false)} onConfirm={() => void removeAllRoutes()}/>} 
  </div></section>;
}

function RouteEditor({ route, token, onUpdated, onDeleteRequest, onSuccess, onError }: { route: Route; token: string; onUpdated: () => Promise<void>; onDeleteRequest: (route: Route) => void; onSuccess: (message: string) => void; onError: (title: string, error: unknown) => void }) {
  const [grade, setGrade] = useState(route.grade);
  const [saving, setSaving] = useState(false);
  const [pendingAction, setPendingAction] = useState<"grade" | null>(null);
  useEffect(() => { setGrade(route.grade); }, [route.version, route.grade]);

  async function save() {
    setSaving(true);
    try { await updateRoute(token, route.id, { grade }, route.version); await onUpdated(); onSuccess(`Категория трассы №${route.number} сохранена`); }
    catch (error) { if (error instanceof ApiError && error.status === 409) await onUpdated(); onError(`Не удалось сохранить трассу №${route.number}`, error); }
    finally { setSaving(false); setPendingAction(null); }
  }
  return <><article className={route.is_active ? "route-config-card compact" : "route-config-card compact inactive"}><strong className="config-route-number" title={`Трасса №${route.number}`}>{route.number}</strong><label className="route-grade-control"><select value={grade} disabled={saving} aria-label={`Категория трассы №${route.number}`} onChange={(event) => { const value = event.target.value; setGrade(value); if (value !== route.grade) setPendingAction("grade"); }}>{ROUTE_GRADES.map((item) => <option key={item}>{item}</option>)}</select></label><div className="route-points-readonly" title={`Очки: ${route.points}`}><strong>{route.points}</strong></div><label className="route-delete-button" title={`Удалить трассу №${route.number}`}><select value="" disabled={saving} aria-label={`Действия с трассой №${route.number}`} onChange={(event) => { if (event.target.value === "delete") onDeleteRequest(route); }}><option value="" disabled>Действия</option><option value="delete">Удалить</option></select><Trash2 size={14}/></label></article>
    {pendingAction === "grade" && <ConfirmDialog title={`Изменить категорию трассы №${route.number}?`} description={`Трасса получит категорию ${grade} и соответствующее ей количество очков.`} confirmLabel="Изменить категорию" busy={saving} onCancel={() => { setGrade(route.grade); setPendingAction(null); }} onConfirm={() => void save()}/>} 
  </>;
}

export type RouteNotification = { type: "success" | "error"; title: string; details?: string };
type RouteSortKey = "number" | "grade" | "points";

function RouteSortButton({ label, sortKey, sort, onSort }: { label: string; sortKey: RouteSortKey; sort: { key: RouteSortKey; direction: "asc" | "desc" }; onSort: (key: RouteSortKey) => void }) {
  const icon = sort.key !== sortKey ? <ArrowUpDown size={14}/> : sort.direction === "asc" ? <ArrowUp size={14}/> : <ArrowDown size={14}/>;
  return <button className={sort.key === sortKey ? "route-sort active" : "route-sort"} onClick={() => onSort(sortKey)}>{label}{icon}</button>;
}

export function RouteToast({ notification, onClose }: { notification: RouteNotification; onClose: () => void }) {
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    if (notification.type !== "success") return;
    const timer = window.setTimeout(onClose, 3500);
    return () => window.clearTimeout(timer);
  }, [notification, onClose]);
  return <div className={`route-toast ${notification.type}`} role={notification.type === "error" ? "alert" : "status"}><div className="toast-main">{notification.type === "success" ? <CircleCheck size={20}/> : <CircleAlert size={20}/>}<strong>{notification.title}</strong><button className="toast-close" onClick={onClose} title="Закрыть"><X size={17}/></button></div>{notification.type === "error" && notification.details && <><button className="toast-details-button" onClick={() => setExpanded((value) => !value)}>{expanded ? <ChevronUp size={15}/> : <ChevronDown size={15}/>}Подробнее</button>{expanded && <div className="toast-details">{notification.details}</div>}</>}</div>;
}
