"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp, CircleAlert, CircleCheck, Plus, Trash2, X, Pencil } from "lucide-react";
import { createUnassignedRoutes, createRouteGroups, deleteAllRoutes, deleteRoute, deleteRouteGroup, getRouteGroups, previewRouteGroup, Route, RouteGroup, RouteGroupInput, updateRoute, updateRouteGroup } from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";

const rangeLabel = (grade: string) => grade.replace(/[–—]/g, "/");
const GRADES = [5, 6, 7, 8].flatMap(level => ["A", "A+", "B", "B+", "C", "C+"].map(suffix => `${level}${suffix}`));
type Draft = RouteGroupInput & { count: number };
const emptyDraft = (): Draft => ({from_grade: "6A+", to_grade: "6B", color: "#00aa55", points: 0, count: 0});
type Confirmation = { title: string; description: string; label: string; apply: () => Promise<unknown> };
export type RouteNotification = { type: "success" | "error"; title: string; details?: string };

export function RoutesSection({routes, token, onUpdated}: {routes: Route[]; token: string; onUpdated: () => Promise<void>}) {
  const formRef = useRef<HTMLFormElement>(null);
  const [groups, setGroups] = useState<RouteGroup[]>([]);
  const [notification, setNotification] = useState<RouteNotification | null>(null);
  const [drafts, setDrafts] = useState<Draft[] | null>(null);
  const [editing, setEditing] = useState<RouteGroup | null>(null);
  const [count, setCount] = useState(75);
  const [filter, setFilter] = useState("");
  const [number, setNumber] = useState("");
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleteMode, setDeleteMode] = useState(false);
  function errorMessage(error: unknown) { setNotification({type: "error", title: "Не удалось сохранить изменения", details: error instanceof Error ? error.message : String(error)}); }
  useEffect(() => {
    let cancelled = false;
    getRouteGroups(token).then(items => { if (!cancelled) setGroups(items); }).catch(error => {
      if (!cancelled) setNotification({type: "error", title: "Не удалось загрузить группы трасс", details: String(error)});
    });
    return () => { cancelled = true; };
  }, [token, routes]);
  const formOpen = drafts !== null;
  useEffect(() => {
    if (formOpen) {
      const catalog = formRef.current?.closest("details");
      if (catalog) catalog.open = true;
      formRef.current?.scrollIntoView({block: "nearest"});
    }
  }, [formOpen, editing?.id]);
  async function refresh() { await onUpdated(); setGroups(await getRouteGroups(token)); }
  async function apply() {
    if (!confirmation) return;
    setBusy(true);
    try {
      await confirmation.apply();
      setConfirmation(null); setDrafts(null); setEditing(null);
      await refresh();
      setNotification({type: "success", title: "Изменения сохранены"});
    } catch(error) { setConfirmation(null); errorMessage(error); await refresh().catch(() => {}); }
    finally { setBusy(false); }
  }
  async function submitDrafts(event: React.FormEvent) {
    event.preventDefault();
    if (!drafts) return;
    if (drafts.some(d => GRADES.indexOf(d.from_grade) > GRADES.indexOf(d.to_grade))) {
      setNotification({type: "error", title: "Категория «от» не может быть сложнее категории «до»"}); return;
    }
    if (!editing) {
      const items = drafts.map(d => ({...d}));
      setConfirmation({title: "Создать категории?", description: `Категорий: ${items.length}. Диапазоны и баллы будут доступны для выбора в таблице трасс.`, label: "Создать", apply: () => createRouteGroups(token, items)});
      return;
    }
    const group = editing;
    const {count: ignored, ...values} = drafts[0];
    void ignored;
    const payload = {...values, expected_version: group.version, expected_route_versions: group.route_versions};
    setBusy(true);
    try {
      const preview = await previewRouteGroup(token, group.id, payload);
      setConfirmation({title: "Сохранить группу трасс?", description: `Трасс в группе: ${preview.affected_routes}. ${preview.points_changed ? `Баллы за трассу: ${group.points} → ${values.points}. Пересчёт затронет участников: ${preview.affected_participants}.` : "Баллы за прохождения останутся прежними."} Номера и сохранённые прохождения сохранятся.`, label: "Сохранить", apply: () => updateRouteGroup(token, group.id, payload)});
    } catch(error) {errorMessage(error);} finally {setBusy(false);}
  }
  function removeRoute(route: Route) {
    setConfirmation({title: `Удалить трассу №${route.number}?`, description: "Удаление возможно только без сохранённых прохождений. Последующие трассы будут перенумерованы.", label: "Удалить", apply: () => deleteRoute(token, route.id, route.version)});
  }
  async function moveRoute(route: Route, groupId: string) {
    const group = groups.find(g => g.id === groupId);
    if (!group) return;
    if (!route.group_id && route.grade === "Не назначена") {
      setBusy(true);
      try { await updateRoute(token, route.id, {group_id: group.id}, route.version); await refresh(); }
      catch (error) { errorMessage(error); await refresh().catch(()=>{}); }
      finally { setBusy(false); }
      return;
    }
    setConfirmation({title: `Перенести трассу №${route.number}?`, description: `Группа: ${rangeLabel(group.grade)}. Баллы: ${route.points} → ${group.points}. Сохранённые результаты будут пересчитаны, прохождения сохранятся.`, label: "Перенести", apply: () => updateRoute(token, route.id, {group_id: group.id}, route.version)});
  }
  const shownRoutes = routes.filter(r => (!filter || (r.group_id ?? "legacy") === filter) && (!number || String(r.number).includes(number.trim())));
  return <section className="routes-config-pane system-relief"><div className="admin-workspace-container route-ranges">
    <header className="config-header admin-section-hero"><div><h1>Трассы</h1><p>{groups.length} групп · {routes.length} трасс · активных {routes.filter(r=>r.is_active).length}</p></div><div className="range-actions">
      <button className="danger-outline-button" disabled={!routes.length || busy} onClick={()=>setConfirmation({title: "Удалить все трассы?", description: "Группы останутся. Удаление недоступно, если сохранены прохождения или назначения судей.", label: "Удалить трассы", apply: ()=>deleteAllRoutes(token)})}><Trash2 size={16}/>Удалить все трассы</button>
      <button className="primary-action" disabled={busy} onClick={()=>{setEditing(null);setDrafts([emptyDraft()]);}}><Plus size={17}/>Добавить категории</button>
    </div></header>
    {notification && <RouteToast notification={notification} onClose={()=>setNotification(null)}/>}
    <p className="range-intro">Создайте категории → добавьте трассы → выберите категорию у каждого номера.</p>
    <details open className="range-group category-catalog"><summary>1. Категории сложности <span>{groups.length}</span></summary>
      {groups.length ? <div className="category-catalog-list">{groups.map(group=><div className="category-compact-item" key={group.id}>
        <span className="range-color" style={{background:group.color}}/><strong title={`Назначено трасс: ${group.route_count}`}>{rangeLabel(group.grade)}</strong><span className="category-points">{group.points} б.</span>
        <div className="range-actions"><button className="category-edit-icon" title="Редактировать категорию" aria-label={`Настроить категорию ${rangeLabel(group.grade)}`} disabled={busy} onClick={()=>{setEditing(group);setDrafts([{...group,count:0}]);}}><Pencil size={13}/></button>
        {group.route_count===0&&<button className="route-delete-button" aria-label={`Удалить категорию ${rangeLabel(group.grade)}`} disabled={busy} onClick={()=>setConfirmation({title:`Удалить категорию ${rangeLabel(group.grade)}?`,description:"Категория не назначена трассам.",label:"Удалить",apply:()=>deleteRouteGroup(token,group)})}><Trash2 size={16}/></button>}</div>
      </div>)}</div>:<p className="range-empty">Создайте категории с диапазонами сложности и баллами.</p>}
    {drafts && <form ref={formRef} className="range-form category-inline-form" onSubmit={submitDrafts}>
      <div className="range-form-title"><h2>{editing ? `Категория ${rangeLabel(editing.grade)}` : "Новая категория"}</h2><button type="button" className="secondary-button" onClick={()=>{setDrafts(null);setEditing(null);}} disabled={busy}>Отмена</button></div>
      {drafts.map((draft,index)=><div className="range-draft-row" key={index}>
        <label>Цвет<input type="color" aria-label={`Цвет группы ${index+1}`} value={draft.color} onChange={e=>setDrafts(ds=>ds!.map((d,i)=>i===index?{...d,color:e.target.value}:d))}/></label>
        <label>От<select aria-label={`Сложность от ${index+1}`} value={draft.from_grade} onChange={e=>setDrafts(ds=>ds!.map((d,i)=>i===index?{...d,from_grade:e.target.value}:d))}>{GRADES.map(g=><option key={g}>{g}</option>)}</select></label>
        <label>До<select aria-label={`Сложность до ${index+1}`} value={draft.to_grade} onChange={e=>setDrafts(ds=>ds!.map((d,i)=>i===index?{...d,to_grade:e.target.value}:d))}>{GRADES.map(g=><option key={g}>{g}</option>)}</select></label>

        <label>Баллы<input aria-label={`Баллы за трассу ${index+1}`} type="number" min="0" max="1000000" required value={draft.points} onChange={e=>setDrafts(ds=>ds!.map((d,i)=>i===index?{...d,points:Number(e.target.value)}:d))}/></label>
        {!editing && drafts.length>1 && <button type="button" className="route-delete-button" aria-label={`Убрать строку ${index+1}`} onClick={()=>setDrafts(ds=>ds!.filter((_,i)=>i!==index))}><Trash2 size={16}/></button>}
      </div>)}
      <div className="range-actions">{!editing && <><button type="button" className="secondary-button" disabled={drafts.length>=24 || busy} onClick={()=>setDrafts(ds=>[...ds!,emptyDraft()])}><Plus size={16}/>Ещё категория</button></>}
        <button className="save-route-button" disabled={busy}>{editing ? "Проверить и сохранить" : "Создать категории"}</button>
      </div>
    </form>}
    </details>
    <section className="range-group route-assignment-section"><header className="range-group-header"><h2>2. Назначение трасс</h2><p>Без категории: {routes.filter(r=>!r.group_id).length}</p></header>
      <div className="assignment-controls"><form className="range-form range-add" onSubmit={e=>{e.preventDefault();const amount=count;setConfirmation({title:`Создать ${amount} трасс?`,description:`Номера продолжат текущий список. Категорию каждой трассы вы выберете вручную. До назначения категории у новой трассы 0 баллов.`,label:"Создать трассы",apply:()=>createUnassignedRoutes(token,amount)});}}>
        <label>Добавить<input aria-label="Количество новых трасс" type="number" min="1" max="100" required value={count} onChange={e=>setCount(Number(e.target.value))}/></label><button className="save-route-button" disabled={busy}>Создать трассы</button>
      </form>
      <div className="range-toolbar"><input data-view-action aria-label="Поиск трассы по номеру" placeholder="№" value={number} onChange={e=>setNumber(e.target.value)}/><select data-view-action aria-label="Фильтр по категории" value={filter} onChange={e=>setFilter(e.target.value)}><option value="">Все категории</option><option value="legacy">Без категории</option>{groups.map(g=><option key={g.id} value={g.id}>{rangeLabel(g.grade)}</option>)}</select><button type="button" className={`route-delete-mode${deleteMode ? " active" : ""}`} aria-pressed={deleteMode} onClick={()=>setDeleteMode(v=>!v)}><Trash2 size={13}/>{deleteMode ? "Закончить удаление" : "Удаление"}</button></div></div>
      <div className="assignment-caption"><span>По 12 трасс в колонке · выбор сохраняется автоматически</span><span>Показано {shownRoutes.length}</span></div>
      <div className="compact-route-grid">{[...shownRoutes].sort((a,b)=>a.number-b.number).map(route=><div className="compact-route-row" key={route.id}>
        {deleteMode ? <button className="route-number-delete" title={`Удалить трассу №${route.number}`} aria-label={`Удалить трассу №${route.number}`} disabled={busy} onClick={()=>removeRoute(route)}><Trash2 size={12}/></button> : <span className="route-static-number">{route.number}</span>}<span className="route-category-select"><select aria-label={`Категория трассы №${route.number}`} value={route.group_id??""} disabled={busy} onChange={e=>moveRoute(route,e.target.value)}>
          {!route.group_id&&<option value="" disabled>—</option>}{groups.map(g=><option key={g.id} value={g.id}>{rangeLabel(g.grade)}</option>)}</select></span>
      </div>)}</div>{!shownRoutes.length&&<p className="range-empty">Трассы не найдены.</p>}
    </section>
    {confirmation&&<ConfirmDialog title={confirmation.title} description={confirmation.description} confirmLabel={confirmation.label} busy={busy} onCancel={()=>setConfirmation(null)} onConfirm={()=>void apply()}/>}
  </div></section>;
}

export function RouteToast({ notification, onClose }: { notification: RouteNotification; onClose: () => void }) {
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    if (notification.type !== "success") return;
    const timer = window.setTimeout(onClose, 3500);
    return () => window.clearTimeout(timer);
  }, [notification, onClose]);
  return <div className={`route-toast ${notification.type}`} role={notification.type === "error" ? "alert" : "status"}><div className="toast-main">{notification.type === "success" ? <CircleCheck size={20}/> : <CircleAlert size={20}/>}<strong>{notification.title}</strong><button data-view-action className="toast-close" onClick={onClose} title="Закрыть"><X size={17}/></button></div>{notification.type === "error" && notification.details && <><button data-view-action className="toast-details-button" onClick={() => setExpanded((value) => !value)}>{expanded ? <ChevronUp size={15}/> : <ChevronDown size={15}/>}Подробнее</button>{expanded && <div className="toast-details">{notification.details}</div>}</>}</div>;
}
