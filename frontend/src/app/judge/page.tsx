"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, LogOut, RotateCcw, Search, ShieldCheck } from "lucide-react";
import { ApiError, CurrentUser, getCurrentUser, getJudgeWorkspace, JudgeParticipant, JudgeWorkspace, logoutSession, saveJudgeResult } from "@/lib/api";
import { ConfirmDialog } from "../admin/components/ConfirmDialog";
import { RoleGuideDialog } from "../admin/components/RoleGuideDialog";

type JudgeAction = "attempt" | "zone" | "top";
type QueueItem = { id: string; actorId: string; eventId: string; routeId: string; finalResultId: string; expectedVersion: number; zoneAttempt: number | null; topAttempt: number | null; attemptCount: number; startNumber: number };

const CACHE_USER = "parkrock_judge_user";
const CACHE_WORKSPACE = "parkrock_judge_workspace";
const QUEUE_KEY = "parkrock_judge_queue";
const DRAFTS_KEY = "parkrock_judge_drafts";

function readStored<T>(key: string, fallback: T): T {
  try { return JSON.parse(localStorage.getItem(key) ?? "") as T; } catch { return fallback; }
}

function resultFromActions(actions: JudgeAction[]) {
  const zoneIndex = actions.findIndex((action) => action === "zone");
  const topIndex = actions.findIndex((action) => action === "top");
  const zoneAttempt = zoneIndex >= 0 ? zoneIndex + 1 : topIndex >= 0 ? topIndex + 1 : null;
  const topAttempt = topIndex >= 0 ? topIndex + 1 : null;
  const score = topAttempt ? 25 - (topAttempt - 1) / 10 : zoneAttempt ? 10 - (zoneAttempt - 1) / 10 : 0;
  return { zoneAttempt, topAttempt, score };
}

export default function JudgePage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [hydrated, setHydrated] = useState(false);
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [workspace, setWorkspace] = useState<JudgeWorkspace | null>(null);
  const [workspaceVerified, setWorkspaceVerified] = useState(false);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<JudgeParticipant | null>(null);
  const [actions, setActions] = useState<JudgeAction[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [connection, setConnection] = useState<"online" | "offline">("online");
  const [showRoleGuide, setShowRoleGuide] = useState(false);
  const flushing = useRef(false);

  useEffect(() => {
    setToken(localStorage.getItem("parkrock_admin_token") ?? "");
    setUser(readStored<CurrentUser | null>(CACHE_USER, null));
    setWorkspace(readStored<JudgeWorkspace | null>(CACHE_WORKSPACE, null));
    setQueue(readStored<QueueItem[]>(QUEUE_KEY, []));
    setHydrated(true);
  }, []);
  useEffect(() => { if (hydrated && !token) router.replace("/admin"); }, [hydrated, token, router]);
  const closeWorkspace = useCallback((message: string) => {
    setWorkspace(null); localStorage.removeItem(CACHE_WORKSPACE);
    setSelected(null); setActions([]); setConfirming(false);
    setWorkspaceVerified(true); setConnection("online"); setError(message);
  }, []);
  const load = useCallback(async (activeToken: string) => {
    try {
      const current = await getCurrentUser(activeToken);
      if (current.role !== "route_judge") { router.replace("/admin"); return; }
      setUser(current); localStorage.setItem(CACHE_USER, JSON.stringify(current));
      if (sessionStorage.getItem("parkrock_show_role_guide") === "1") {
        sessionStorage.removeItem("parkrock_show_role_guide"); setShowRoleGuide(true);
      }
      const data = await getJudgeWorkspace(activeToken);
      setWorkspace(data); localStorage.setItem(CACHE_WORKSPACE, JSON.stringify(data)); setWorkspaceVerified(true); setError(""); setConnection("online");
      setSelected((value) => value ? data.participants.find((item) => item.final_result_id === value.final_result_id) ?? null : null);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) {
        localStorage.removeItem("parkrock_admin_token"); setToken(""); setUser(null); router.replace("/admin"); return;
      }
      if (cause instanceof ApiError && cause.status === 409) {
        closeWorkspace(cause.message); return;
      }
      setConnection("offline");
      if (!readStored<JudgeWorkspace | null>(CACHE_WORKSPACE, null)) setError(cause instanceof Error ? cause.message : "Не удалось загрузить рабочее место");
    }
  }, [closeWorkspace, router]);
  useEffect(() => { if (token) void load(token); }, [token, load]);
  useEffect(() => {
    if (!token) return;
    const interval = window.setInterval(() => void load(token), 3000);
    return () => window.clearInterval(interval);
  }, [token, load]);

  const persistQueue = useCallback((items: QueueItem[]) => {
    setQueue(items); localStorage.setItem(QUEUE_KEY, JSON.stringify(items));
  }, []);
  const flushQueue = useCallback(async () => {
    if (!token || !workspaceVerified || workspace?.stage !== "final" || !queue.length || flushing.current) return;
    flushing.current = true;
    let remaining = [...queue];
    try {
      for (const item of queue.filter((queued) => queued.actorId === user?.id && queued.eventId === workspace?.event_id && queued.routeId === workspace?.route.id)) {
        try {
          const data = await saveJudgeResult(token, item.finalResultId, item.expectedVersion, item.zoneAttempt, item.topAttempt, item.id);
          remaining = remaining.filter((queued) => queued.id !== item.id);
          setWorkspace(data); localStorage.setItem(CACHE_WORKSPACE, JSON.stringify(data)); setConnection("online");
        } catch (cause) {
          if (cause instanceof ApiError && cause.status === 409) {
            try {
              const data = await getJudgeWorkspace(token);
              const serverRow = data.participants.find((row) => row.final_result_id === item.finalResultId);
              setWorkspace(data); localStorage.setItem(CACHE_WORKSPACE, JSON.stringify(data)); setConnection("online");
              if (serverRow?.locked && serverRow.zone_attempt === item.zoneAttempt && serverRow.top_attempt === item.topAttempt) {
                remaining = remaining.filter((queued) => queued.id !== item.id);
              } else setError(`Результат участника №${item.startNumber} изменён на сервере. Обратитесь к главному судье.`);
            } catch (refreshCause) {
              if (refreshCause instanceof ApiError && refreshCause.status === 409) closeWorkspace(refreshCause.message);
              else setConnection("offline");
            }
          } else setConnection("offline");
        }
      }
      const delivered = new Set(queue.filter((item) => !remaining.some((pending) => pending.id === item.id)).map((item) => item.id));
      setQueue((current) => {
        const next = current.filter((item) => !delivered.has(item.id));
        localStorage.setItem(QUEUE_KEY, JSON.stringify(next));
        return next;
      });
      if (queue.length && !remaining.length) setNotice("Все ожидавшие результаты сохранены на сервере");
    } finally { flushing.current = false; }
  }, [token, user?.id, workspace?.event_id, workspace?.route.id, workspace?.stage, workspaceVerified, queue, closeWorkspace]);
  useEffect(() => {
    if (!token) return;
    const send = () => void flushQueue();
    const interval = window.setInterval(send, 5000);
    window.addEventListener("online", send);
    send();
    return () => { window.clearInterval(interval); window.removeEventListener("online", send); };
  }, [token, flushQueue]);

  const rows = useMemo(() => {
    const value = search.trim().toLocaleLowerCase("ru");
    if (!value) return workspace?.participants ?? [];
    return (workspace?.participants ?? []).filter((item) =>
      String(item.start_number).includes(value) || item.full_name.toLocaleLowerCase("ru").includes(value),
    );
  }, [workspace, search]);
  const draftResult = useMemo(() => resultFromActions(actions), [actions]);
  const queuedSelected = selected ? queue.find((item) => item.finalResultId === selected.final_result_id) : undefined;
  const pendingIds = useMemo(() => new Set(queue.map((item) => item.finalResultId)), [queue]);
  const result = queuedSelected ? { zoneAttempt: queuedSelected.zoneAttempt, topAttempt: queuedSelected.topAttempt, score: queuedSelected.topAttempt ? 25 - (queuedSelected.topAttempt - 1) / 10 : queuedSelected.zoneAttempt ? 10 - (queuedSelected.zoneAttempt - 1) / 10 : 0 } : selected?.locked ? { zoneAttempt: selected.zone_attempt, topAttempt: selected.top_attempt, score: selected.score } : draftResult;
  const topReached = actions.includes("top");
  useEffect(() => {
    if (!selected || selected.locked || queuedSelected) return;
    const drafts = readStored<Record<string, JudgeAction[]>>(DRAFTS_KEY, {});
    if (actions.length) drafts[selected.final_result_id] = actions;
    else delete drafts[selected.final_result_id];
    localStorage.setItem(DRAFTS_KEY, JSON.stringify(drafts));
  }, [selected, actions, queuedSelected]);

  function chooseParticipant(item: JudgeParticipant) {
    if (!workspaceVerified || workspace?.stage !== "final") return;
    const drafts = readStored<Record<string, JudgeAction[]>>(DRAFTS_KEY, {});
    setSelected(item); setActions(drafts[item.final_result_id] ?? []); setNotice(""); setError("");
  }
  function addAction(action: JudgeAction) {
    if (!workspaceVerified || workspace?.stage !== "final" || !selected || selected.locked || queuedSelected || topReached) return;
    if (action === "zone" && actions.includes("zone")) return;
    setActions((current) => [...current, action]);
  }
  function save() {
    if (!workspaceVerified || workspace?.stage !== "final" || !selected || !user) return;
    setSaving(true);
    const item: QueueItem = {
      id: crypto.randomUUID(), actorId: user.id, eventId: workspace.event_id, routeId: workspace.route.id,
      finalResultId: selected.final_result_id, expectedVersion: selected.version,
      zoneAttempt: result.zoneAttempt, topAttempt: result.topAttempt,
      attemptCount: actions.length, startNumber: selected.start_number,
    };
    persistQueue([...queue, item]);
    const drafts = readStored<Record<string, JudgeAction[]>>(DRAFTS_KEY, {});
    delete drafts[selected.final_result_id]; localStorage.setItem(DRAFTS_KEY, JSON.stringify(drafts));
    setSelected(null); setActions([]); setSearch(""); setConfirming(false); setSaving(false); setError("");
    setNotice(navigator.onLine ? `Результат участника №${item.startNumber} принят и отправляется` : `Результат участника №${item.startNumber} ожидает отправки`);
  }
  function logout() {
    void logoutSession(token).catch(() => undefined);
    localStorage.removeItem("parkrock_admin_token"); localStorage.removeItem(CACHE_USER); localStorage.removeItem(CACHE_WORKSPACE); localStorage.removeItem(DRAFTS_KEY);
    setToken(""); setUser(null); setWorkspace(null); setWorkspaceVerified(false);
    router.replace("/admin");
  }

  if (!hydrated || !token || !user) return <main className="auth-redirect" aria-live="polite"><img className="brand-logo loading-brand-logo" src="/brand/parkrock-white.svg" alt="ПаркРок"/><strong>Открываем единый вход…</strong></main>;

  return <main className="judge-page">
    <header className="judge-header"><img className="brand-logo judge-brand-logo" src="/brand/parkrock-white.svg" alt="ПаркРок"/><div className="judge-route-mark">{workspace?.route.number ?? "—"}</div><div><span>Финальная трасса</span><strong>{workspace?.route.name ?? "Загрузка..."}</strong></div><div className="judge-header-user"><span>{user.full_name}</span><button onClick={logout} title="Выйти"><LogOut size={20}/></button></div></header>
    <div className="judge-shell">
      {connection === "offline" && <div className="judge-offline">Нет связи · результаты сохраняются на этом ноутбуке</div>}
      {notice && <div className="judge-notice"><CheckCircle2 size={20}/>{notice}</div>}
      {error && <div className="judge-error">{error}</div>}
      {!workspaceVerified || workspace?.stage !== "final" ? <section className="judge-empty"><strong>{workspaceVerified ? "Рабочее место пока недоступно" : "Проверяем стадию соревнований"}</strong><span>{error || "Ожидаем запуск финала"}</span></section> : <>
        <section className="judge-search"><label><Search size={22}/><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Стартовый номер или ФИО" autoFocus/></label><span>{rows.filter((item) => !item.locked && !pendingIds.has(item.final_result_id)).length} ожидают результата</span></section>
        {!selected ? <section className="judge-participants">{rows.map((item) => { const pending = pendingIds.has(item.final_result_id); return <button key={item.final_result_id} className={item.locked ? "locked" : pending ? "pending" : ""} onClick={() => chooseParticipant(item)}><span className="judge-bib">{item.start_number}</span><span><strong>{item.full_name}</strong><small>{item.category_name} · выход {item.exit_order ?? "—"} · {item.club}</small></span><span className="judge-row-status">{item.locked ? <><ShieldCheck size={18}/>Сохранено на сервере</> : pending ? "Ожидает отправки" : "Выбрать"}</span></button>; })}{!rows.length && <div className="judge-empty">Участники не найдены</div>}</section> : <section className="judge-card">
          <div className="judge-athlete"><button onClick={() => { setSelected(null); setActions([]); }}>← К списку</button><span className="judge-bib large">{selected.start_number}</span><div><h1>{selected.full_name}</h1><p>{selected.category_name} · выход {selected.exit_order ?? "—"} · квалификация: {selected.qualification_place} место</p></div></div>
          {selected.locked ? <div className="judge-locked-note"><ShieldCheck size={22}/>Результат сохранён. Изменение доступно секретарю, главному судье и администратору.</div> : queuedSelected ? <div className="judge-pending-note">Результат сохранён на ноутбуке и ожидает отправки на сервер.</div> : <><div className="judge-attempt"><span>Текущая попытка</span><strong>{actions.length + 1}</strong></div><div className="judge-actions"><button className="attempt" disabled={topReached} onClick={() => addAction("attempt")}>ПОПЫТКА</button><button className="zone" disabled={topReached || actions.includes("zone")} onClick={() => addAction("zone")}>ЗОНА</button><button className="top" disabled={topReached} onClick={() => addAction("top")}>ТОП</button></div></>}
          <div className="judge-summary"><div><span>Попыток</span><strong>{queuedSelected?.attemptCount ?? (selected.locked ? (result.topAttempt ?? result.zoneAttempt ?? "—") : actions.length)}</strong></div><div><span>Зона</span><strong>{result.zoneAttempt ?? "—"}</strong></div><div><span>Топ</span><strong>{result.topAttempt ?? "—"}</strong></div><div><span>Баллы</span><strong>{result.score.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}</strong></div></div>
          {!selected.locked && !queuedSelected && <div className="judge-controls"><button className="judge-undo" disabled={!actions.length} onClick={() => setActions((current) => current.slice(0, -1))}><RotateCcw size={20}/>Отменить последнее действие</button><button className="judge-save" disabled={!actions.length} onClick={() => setConfirming(true)}>Проверить и сохранить</button></div>}
        </section>}
      </>}
    </div>
    {confirming && selected && <ConfirmDialog title={`Сохранить результат участника №${selected.start_number}?`} description="После второго подтверждения судья не сможет изменить этот результат." confirmLabel="Подтвердить результат" busy={saving} onCancel={() => setConfirming(false)} onConfirm={() => void save()}><div className="judge-confirm-grid"><span>Попыток<strong>{actions.length}</strong></span><span>Зона<strong>{result.zoneAttempt ?? "—"}</strong></span><span>Топ<strong>{result.topAttempt ?? "—"}</strong></span><span>Баллы<strong>{result.score.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}</strong></span></div></ConfirmDialog>}
    {showRoleGuide && <RoleGuideDialog role="route_judge" onClose={() => setShowRoleGuide(false)}/>}
  </main>;
}
