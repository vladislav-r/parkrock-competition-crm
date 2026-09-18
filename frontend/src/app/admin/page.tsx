"use client";
import { ReadOnlyScope } from "./components/ReadOnlyScope";
import { CrmLogo } from "./components/CrmLogo";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Archive, Building2, CheckCircle2, ChevronLeft, FileSpreadsheet, Flag, Layers3, LockKeyhole, Menu, MoreVertical, Mountain, Pencil, Plus, Settings, Trash2, Trophy, Unlock, Users, X } from "lucide-react";
import { ApiError, CompetitionSet, confirmParticipantCheckIn, confirmSet, createSet, CurrentUser, deleteSet, EventInfo, getAdminEvent, getCurrentUser, getParticipants, login, logoutSession, Participant, reopenSet, ReceptionStatusUpdate, SetPayload, updateParticipantReception, updateParticipantResults, updateParticipantSet, updateSet } from "@/lib/api";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { ParticipantCreateDialog, ParticipantImportDialog } from "./components/ParticipantDialogs";
import { ParticipantEditDialog } from "./components/ParticipantEditDialog";
import { ParticipantsSection } from "./components/ParticipantsSection";
import { RoutesSection, RouteToast, type RouteNotification } from "./components/RoutesSection";
import { SettingsSection } from "./components/SettingsSection";
import { ClubsSection } from "./components/ClubsSection";
import { SetActionDialog, type SetActionState, SetEditorDialog, type SetEditorState } from "./components/SetDialogs";
import { FinalSection } from "./components/FinalSection";
import { ApplicationsSection } from "./components/ApplicationsSection";
import { BackupsSection } from "./components/BackupsSection";
import { CategoriesSection } from "./components/CategoriesSection";
import { QualificationSection } from "./components/QualificationSection";
import { RoleGuideDialog } from "./components/RoleGuideDialog";
import { ExportsSection } from "./components/ExportsSection";
import "./relief.css";
import "./clubs-relief.css";
import "./stages-relief.css";
import "./categories-relief.css";
import "./applications-relief.css";
import "./confirmations-relief.css";
import "./system-relief.css";
import "./presence.css";
import "./mobile-shell.css";
import { usePresence } from "@/lib/usePresence";
import { SyncStatus } from "./components/SyncStatus";
import { UserMenu } from "./components/UserMenu";

function errorDetails(error: unknown) {
  return error instanceof ApiError ? `Код ответа: ${error.status}` : error instanceof Error ? error.message : "Неизвестная ошибка";
}

function formatSetDate(value: string) {
  return value.split("-").reverse().join(".");
}

export default function AdminPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  usePresence(token);
  const [hydrated, setHydrated] = useState(false);
  const [currentUser, setCurrentUser] = useState<CurrentUser | null>(null);
  const readOnly = !!currentUser?.permissions.includes("system.read_only");
  // These keys open sections only; ReadOnlyScope disables data controls.
  const sectionPermissions = readOnly ? ["dashboard.view", "participants.view", "participants.import", "final.manage", "exports.create", "routes.manage", "categories.manage", "users.manage", "roles.manage", "audit.view", "publication.manage", "export_settings.manage", "competition.reset", "demo.manage", "backups.manage"] : (currentUser?.permissions ?? []);
  const [event, setEvent] = useState<EventInfo | null>(null);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [selectedSet, setSelectedSet] = useState("");
  const [requestedParticipantId, setRequestedParticipantId] = useState("");
  const [selected, setSelected] = useState<Participant | null>(null);
  const [editingParticipant, setEditingParticipant] = useState<Participant | null>(null);
  const [search, setSearch] = useState("");
  const [error, setError] = useState("");
  const [editingResults, setEditingResults] = useState(false);
  const [draftCompletedRoutes, setDraftCompletedRoutes] = useState<Set<string>>(new Set());
  const [resultsSaving, setResultsSaving] = useState(false);
  const [resultsNotification, setResultsNotification] = useState<RouteNotification | null>(null);
  const [section, setSection] = useState<"participants" | "applications" | "clubs" | "qualification" | "final" | "exports" | "routes" | "categories" | "settings" | "backups">("participants");
  const [showRoleGuide, setShowRoleGuide] = useState(false);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const navigationRef = useRef<HTMLElement>(null);
  const navigationButtonRef = useRef<HTMLButtonElement>(null);
  const [pendingSetId, setPendingSetId] = useState("");
  const [participantDialog, setParticipantDialog] = useState<"import" | "create" | null>(null);
  const [importNotification, setImportNotification] = useState<RouteNotification | null>(null);
  const [openSetMenuId, setOpenSetMenuId] = useState("");
  const [setEditor, setSetEditor] = useState<SetEditorState | null>(null);
  const [setAction, setSetAction] = useState<SetActionState | null>(null);
  const [setsSaving, setSetsSaving] = useState(false);
  const [setNotification, setSetNotification] = useState<RouteNotification | null>(null);
  const [lastSyncedAt, setLastSyncedAt] = useState<number | null>(null);
  const [syncDuration, setSyncDuration] = useState<number | null>(null);
  const [participantAction, setParticipantAction] = useState<"results" | "check-in" | "cancel-check-in" | "pay" | "unpay" | "merch-issue" | "merch-unissue" | null>(null);
  const [participantActionSaving, setParticipantActionSaving] = useState(false);

  useEffect(() => {
    if (!navigationOpen) return;
    const media = window.matchMedia("(max-width: 760px)");
    if (!media.matches) { setNavigationOpen(false); return; }
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    navigationRef.current?.querySelector<HTMLButtonElement>(".mobile-navigation-close")?.focus();
    const closeOnDesktop = () => { if (!media.matches) setNavigationOpen(false); };
    const onKeyDown = (event: KeyboardEvent) => {
      if (document.querySelector(".modal-backdrop")) return;
      if (event.key === "Escape") { event.preventDefault(); setNavigationOpen(false); }
      if (event.key !== "Tab") return;
      const items = Array.from(navigationRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled), [tabindex="0"]') ?? []).filter(item => item.getClientRects().length);
      const first = items[0], last = items.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", onKeyDown);
    media.addEventListener("change", closeOnDesktop);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
      media.removeEventListener("change", closeOnDesktop);
      navigationButtonRef.current?.focus();
    };
  }, [navigationOpen]);

  useEffect(() => { setToken(localStorage.getItem("parkrock_admin_token") ?? ""); setHydrated(true); }, []);
  useEffect(() => {
    if (!token) { setCurrentUser(null); return; }
    void getCurrentUser(token).then((user) => {
      setCurrentUser(user);
      if (sessionStorage.getItem("parkrock_show_role_guide") === "1" && user.role !== "route_judge") {
        sessionStorage.removeItem("parkrock_show_role_guide"); setShowRoleGuide(true);
      }
      if (user.role === "route_judge" && !user.permissions.some((permission) => !["dashboard.view", "participants.view", "judge.results", "users.presence"].includes(permission))) router.replace("/judge");
    }).catch((cause) => {
      setCurrentUser(null);
      if (cause instanceof ApiError && cause.status === 401) {
        localStorage.removeItem("parkrock_admin_token"); setToken(""); setError("Сеанс завершён. Войдите снова.");
      } else setError(cause instanceof Error ? cause.message : "Не удалось проверить учётную запись");
    });
  }, [token, router]);
  const load = useCallback(async (forceSelected = false) => {
    if (!token || !currentUser) return;
    const startedAt = performance.now();
    try {
      const [eventData, people] = await Promise.all([getAdminEvent(token), getParticipants(token, selectedSet, search)]);
      setEvent(eventData); setParticipants(people); setLastSyncedAt(Date.now()); setSyncDuration(Math.round(performance.now() - startedAt));
      setSelected((current) => {
        if (!current) return null;
        const fresh = people.find((person) => person.id === current.id) ?? null;
        if (!forceSelected && editingResults && fresh && fresh.version !== current.version) {
          setResultsNotification({ type: "error", title: "Карточка изменена на другом рабочем месте", details: "Черновик сохранен локально. Отмените редактирование и откройте карточку заново." });
          return current;
        }
        return fresh;
      });
    } catch { /* Ошибки чтения отображает общий SyncStatus. */ }
  }, [token, currentUser, selectedSet, search, editingResults]);
  useEffect(() => {
    const initial = window.setTimeout(() => void load(), 200);
    const interval = window.setInterval(() => void load(), 3000);
    const refresh = () => void load();
    window.addEventListener("online", refresh);
    window.addEventListener("focus", refresh);
    return () => { window.clearTimeout(initial); window.clearInterval(interval); window.removeEventListener("online", refresh); window.removeEventListener("focus", refresh); };
  }, [load]);
  useEffect(() => {
    if (!requestedParticipantId || selectedSet || search) return;
    const person = participants.find((item) => item.id === requestedParticipantId);
    if (person) { setSelected(person); setRequestedParticipantId(""); }
  }, [participants, requestedParticipantId, selectedSet, search]);
  useEffect(() => { setPendingSetId(""); }, [selected?.id]);
  useEffect(() => {
    setEditingResults(false);
    setDraftCompletedRoutes(new Set(selected?.ascents.filter((item) => item.completed).map((item) => item.route_id) ?? []));
  }, [selected?.id]);

  const activeSet = useMemo(() => event?.sets.find((item) => item.id === (selected?.set_id ?? selectedSet)), [event, selected, selectedSet]);
  const isLocked = activeSet?.status === "confirmed";
  const currentSetId = useMemo(() => event?.sets.find((item) => item.status === "reopened")?.id
    ?? event?.sets.find((item) => item.status === "draft")?.id, [event]);
  const pendingSet = useMemo(() => event?.sets.find((item) => item.id === pendingSetId), [event, pendingSetId]);

  function setItemClass(item: CompetitionSet) {
    return [selectedSet === item.id ? "active" : "", item.status === "confirmed" ? "set-completed" : "", currentSetId === item.id ? "set-current" : ""].filter(Boolean).join(" ");
  }

  async function handleLogin(formData: FormData) {
    try { const value = await login(String(formData.get("email")), String(formData.get("password"))); localStorage.setItem("parkrock_admin_token", value); sessionStorage.setItem("parkrock_show_role_guide", "1"); setToken(value); setError(""); }
    catch (e) { setError(e instanceof Error ? e.message : "Не удалось войти"); }
  }
  function logout() { void logoutSession(token).catch(() => undefined); localStorage.removeItem("parkrock_admin_token"); setToken(""); setEvent(null); setCurrentUser(null); }
  function beginResultsEditing() {
    if (!selected) return;
    setDraftCompletedRoutes(new Set(selected.ascents.filter((item) => item.completed).map((item) => item.route_id)));
    setEditingResults(true); setResultsNotification(null);
  }
  function toggleDraftRoute(routeId: string) {
    setDraftCompletedRoutes((current) => {
      const next = new Set(current);
      if (next.has(routeId)) next.delete(routeId); else next.add(routeId);
      return next;
    });
  }
  function cancelResultsEditing() {
    if (!selected) return;
    setDraftCompletedRoutes(new Set(selected.ascents.filter((item) => item.completed).map((item) => item.route_id)));
    setEditingResults(false);
  }
  async function saveResults() {
    if (!selected) return;
    setResultsSaving(true); setResultsNotification(null);
    try {
      const updated = await updateParticipantResults(token, selected.id, Array.from(draftCompletedRoutes), selected.version);
      setSelected(updated); setParticipants((rows) => rows.map((person) => person.id === updated.id ? updated : person));
      setDraftCompletedRoutes(new Set(updated.ascents.filter((item) => item.completed).map((item) => item.route_id)));
      setEditingResults(false); setError("");
      setResultsNotification({ type: "success", title: `Результаты участника №${updated.start_number} сохранены` });
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) { setEditingResults(false); await load(true); }
      setResultsNotification({ type: "error", title: e instanceof Error ? e.message : "Не удалось сохранить результаты", details: errorDetails(e) });
    } finally { setResultsSaving(false); setParticipantAction(null); }
  }
  async function changeSet(setId: string) {
    if (!selected) return;
    try { const updated = await updateParticipantSet(token, selected.id, setId, selected.version); setSelected(updated); setPendingSetId(""); await load(); setError(""); }
    catch (e) { if (e instanceof ApiError && e.status === 409) await load(true); setError(e instanceof Error ? e.message : "Не удалось переместить участника"); }
  }
  async function confirmEntry() {
    if (!selected) return;
    setParticipantActionSaving(true);
    try { const updated = await confirmParticipantCheckIn(token, selected.id, selected.version); setSelected(updated); await load(); setError(""); }
    catch (e) { if (e instanceof ApiError && e.status === 409) await load(true); setError(e instanceof Error ? e.message : "Не удалось подтвердить вход"); }
    finally { setParticipantActionSaving(false); setParticipantAction(null); }
  }
  async function changeReceptionStatus() {
    if (!selected || !participantAction) return;
    const changes: Record<string, ReceptionStatusUpdate> = {
      "cancel-check-in": { checked_in: false }, pay: { is_paid: true }, unpay: { is_paid: false },
      "merch-issue": { merch_issued: true }, "merch-unissue": { merch_issued: false },
    };
    const update = changes[participantAction];
    if (!update) return;
    setParticipantActionSaving(true);
    try { const fresh = await updateParticipantReception(token, selected.id, selected.version, update); setSelected(fresh); await load(); setError(""); }
    catch (e) { if (e instanceof ApiError && e.status === 409) await load(true); setError(e instanceof Error ? e.message : "Не удалось изменить статус"); }
    finally { setParticipantActionSaving(false); setParticipantAction(null); }
  }
  async function saveSet(payload: SetPayload) {
    if (!setEditor) return;
    setSetsSaving(true); setSetNotification(null);
    try {
      const editedName = setEditor.mode === "edit" ? setEditor.item.name : payload.name;
      if (setEditor.mode === "create") await createSet(token, payload);
      else await updateSet(token, setEditor.item.id, payload, setEditor.item.version);
      setSetEditor(null); await load();
      setSetNotification({ type: "success", title: setEditor.mode === "create" ? `Сет «${payload.name}» создан` : `Сет «${editedName}» успешно обновлён` });
    } catch (e) {
      setSetNotification({ type: "error", title: e instanceof Error ? e.message : "Не удалось сохранить сет", details: errorDetails(e) });
    } finally { setSetsSaving(false); }
  }
  async function applySetAction() {
    if (!setAction) return;
    setSetsSaving(true); setSetNotification(null);
    try {
      if (setAction.action === "confirm") await confirmSet(token, setAction.item.id, setAction.item.version);
      else if (setAction.action === "reopen") await reopenSet(token, setAction.item.id, setAction.item.version);
      else await deleteSet(token, setAction.item.id, setAction.item.version);
      const title = setAction.action === "confirm" ? `Сет «${setAction.item.name}» подтверждён`
        : setAction.action === "reopen" ? `Сет «${setAction.item.name}» открыт для изменений`
        : `Сет «${setAction.item.name}» удалён`;
      if (setAction.action === "delete" && selectedSet === setAction.item.id) { setSelectedSet(""); setSelected(null); }
      setSetAction(null); await load(); setSetNotification({ type: "success", title });
    } catch (e) {
      setSetNotification({ type: "error", title: e instanceof Error ? e.message : "Не удалось выполнить действие с сетом", details: errorDetails(e) });
    } finally { setSetsSaving(false); }
  }
  if (!hydrated || (token && !currentUser)) return <main className="auth-redirect" aria-live="polite"><CrmLogo variant="compact"/><strong>{error || "Проверяем учётную запись…"}</strong>{error && <button onClick={() => window.location.reload()}>Повторить подключение</button>}</main>;
  if (!token) return <main className="login-page"><section className="login-panel"><a href="/" className="back-link"><ChevronLeft size={18}/>Онлайн-результаты</a><CrmLogo/><h1>Вход в систему</h1><p>Единый вход для администрации, секретарей и судей на трассе.</p><form action={handleLogin}><label>Электронная почта<input name="email" type="email" autoComplete="username" placeholder="name@example.com" required/></label><label>Пароль<input name="password" type="password" autoComplete="current-password" required/></label>{error && <div className="form-error">{error}</div>}<button className="primary-button">Войти</button></form></section></main>;

  const receptionActionTitle: Record<string, string> = { "cancel-check-in": "Отменить прибытие?", pay: "Подтвердить оплату?", unpay: "Отменить оплату?", "merch-issue": "Подтвердить выдачу мерча?", "merch-unissue": "Отменить выдачу мерча?" };

  return <ReadOnlyScope enabled={readOnly}><main className={`admin-page relief-admin${section === "participants" ? " relief-participants" : ""}`}>
    <header className="admin-header"><button data-view-action ref={navigationButtonRef} className="admin-navigation-toggle" aria-label="Открыть меню разделов" aria-expanded={navigationOpen} aria-controls="admin-navigation" onClick={() => setNavigationOpen(!navigationOpen)}><Menu size={24}/></button><div className="admin-brand"><CrmLogo variant="header"/></div><div className="header-actions">{(currentUser?.role === "route_judge" || !!currentUser?.assigned_final_route_id) && <a href="/judge">Судейство</a>}{readOnly && <span role="status" className="readonly-status">Только просмотр</span>}<SyncStatus lastSyncedAt={lastSyncedAt} duration={syncDuration}/><a href="/" target="_blank">Открыть результаты</a><UserMenu token={token} user={currentUser!} onGuide={() => setShowRoleGuide(true)} onSettings={sectionPermissions.some((permission) => ["users.manage", "roles.manage", "audit.view", "publication.manage", "export_settings.manage", "competition.reset", "demo.manage", "backups.manage"].includes(permission)) ? () => setSection("settings") : undefined} onLogout={logout}/></div></header>
    {navigationOpen && <button data-view-action className="admin-navigation-backdrop" aria-label="Закрыть меню разделов" tabIndex={-1} onClick={() => setNavigationOpen(false)}/>}
    <div className="admin-layout">
      <aside data-view-action ref={navigationRef} role={navigationOpen ? "dialog" : undefined} aria-modal={navigationOpen || undefined} id="admin-navigation" aria-label="Разделы и сеты" className={`sets-sidebar${navigationOpen ? " mobile-open" : ""}`} onClick={(event) => { if ((event.target as Element).closest(".section-item, .set-select-button, .all-participants") && window.matchMedia("(max-width: 760px)").matches) { setNavigationOpen(false); document.querySelector<HTMLButtonElement>(".admin-navigation-toggle")?.focus(); } }}>
        <div className="mobile-navigation-heading"><strong>Разделы и сеты</strong><button data-view-action className="mobile-navigation-close" aria-label="Закрыть меню" onClick={() => setNavigationOpen(false)}><X size={22}/></button></div>
        <div className="sidebar-heading"><span>Работа</span></div>
        <button data-view-action className={section === "participants" ? "section-item active" : "section-item"} onClick={() => setSection("participants")}><Users size={18}/>Участники</button>
        {sectionPermissions.includes("participants.view") && <button data-view-action className={section === "clubs" ? "section-item active" : "section-item"} onClick={() => setSection("clubs")}><Building2 size={18}/>Клубы</button>}
        {sectionPermissions.includes("participants.import") && <button data-view-action className={section === "applications" ? "section-item active" : "section-item"} onClick={() => setSection("applications")}><FileSpreadsheet size={18}/>Заявки</button>}
        {sectionPermissions.includes("final.manage") && <button data-view-action className={section === "qualification" ? "section-item active" : "section-item"} onClick={() => setSection("qualification")}><Flag size={18}/>Квалификация</button>}
        {sectionPermissions.includes("final.manage") && <button data-view-action className={section === "final" ? "section-item active" : "section-item"} onClick={() => setSection("final")}><Trophy size={18}/>Финал</button>}
        {sectionPermissions.includes("exports.create") && <button data-view-action className={section === "exports" ? "section-item active" : "section-item"} onClick={() => setSection("exports")}><FileSpreadsheet size={18}/>Выгрузки</button>}
        {sectionPermissions.some((permission) => ["routes.manage", "categories.manage"].includes(permission)) && <div className="sidebar-config-group"><div className="sidebar-heading"><span>Конфигурация</span></div>{sectionPermissions.includes("routes.manage") && <button data-view-action className={section === "routes" ? "section-item active" : "section-item"} onClick={() => setSection("routes")}><Mountain size={18}/>Трассы</button>}{sectionPermissions.includes("categories.manage") && <button data-view-action className={section === "categories" ? "section-item active" : "section-item"} onClick={() => setSection("categories")}><Layers3 size={18}/>Категории</button>}</div>}
        {(sectionPermissions.some((permission) => ["users.manage", "roles.manage", "audit.view", "publication.manage", "export_settings.manage", "competition.reset", "demo.manage", "backups.manage"].includes(permission)) || sectionPermissions.includes("backups.manage")) && <div className="sidebar-system-group"><div className="sidebar-heading"><span>Система</span></div><button data-view-action className={section === "settings" ? "section-item active" : "section-item"} onClick={() => setSection("settings")}><Settings size={18}/>Настройки</button>{sectionPermissions.includes("backups.manage") && <button data-view-action className={section === "backups" ? "section-item active" : "section-item"} onClick={() => setSection("backups")}><Archive size={18}/>Резервные копии</button>}</div>}
        {section === "participants" && <>
          <div className="sidebar-heading sets-heading"><span>Сеты</span><span className="sets-heading-actions"><small>{event?.sets.length ?? 0}</small><button onClick={() => setSetEditor({ mode: "create" })} title="Добавить сет"><Plus size={16}/></button></span></div>
          <button data-view-action className={!selectedSet ? "set-item all-participants active" : "set-item all-participants"} onClick={() => { setSelectedSet(""); setSelected(null); setOpenSetMenuId(""); }}><span><Users size={18}/>Все участники</span><strong>{event?.participant_count ?? 0}</strong></button>
          {event?.sets.map((item) => <div key={item.id} className={`set-row ${setItemClass(item)}`}>
            <button data-view-action className="set-select-button" onClick={() => { setSelectedSet(item.id); setSelected(null); setOpenSetMenuId(""); }}>
              <span className="set-row-title"><Layers3 size={20}/><strong className="set-name">{item.name}</strong>{item.status === "confirmed" ? <LockKeyhole size={14}/> : null}<span className="capacity">{item.participant_count}/{item.capacity}</span></span>
              {item.scheduled_on && <small className="set-date">{formatSetDate(item.scheduled_on)}</small>}
              <small className="set-row-meta">{item.time_label} · пришли {item.checked_in_count}</small>
            </button>
            <button className="set-menu-button" onClick={() => setOpenSetMenuId((value) => value === item.id ? "" : item.id)} title={`Действия с ${item.name}`} aria-expanded={openSetMenuId === item.id}><MoreVertical size={17}/></button>
            {openSetMenuId === item.id && <><button className="set-menu-backdrop" aria-label="Закрыть меню" onClick={() => setOpenSetMenuId("")}/><div className="set-actions-menu" role="menu">
              <button role="menuitem" disabled={item.status === "confirmed"} onClick={() => { setSetEditor({ mode: "edit", item }); setOpenSetMenuId(""); }}><Pencil size={15}/>Редактировать</button>
              {item.status === "confirmed"
                ? <button role="menuitem" onClick={() => { setSetAction({ action: "reopen", item }); setOpenSetMenuId(""); }}><Unlock size={15}/>Открыть сет</button>
                : <button role="menuitem" onClick={() => { setSetAction({ action: "confirm", item }); setOpenSetMenuId(""); }}><CheckCircle2 size={15}/>Подтвердить сет</button>}
              <button role="menuitem" className="danger-menu-item" disabled={item.status === "confirmed" || item.participant_count > 0} onClick={() => { setSetAction({ action: "delete", item }); setOpenSetMenuId(""); }}><Trash2 size={15}/>Удалить пустой сет</button>
            </div></>}
          </div>)}
        </>}

      </aside>
      {section === "participants" ? <>
      <ParticipantsSection
        openRequested={Boolean(requestedParticipantId)}
        token={token} onDeleted={() => void load(true)}
        event={event} participants={participants} selected={selected} search={search} error={error}
        isLocked={Boolean(isLocked)} editingResults={editingResults} resultsSaving={resultsSaving}
        draftCompletedRoutes={draftCompletedRoutes} activeSetName={activeSet?.name}
        onSearchChange={(value) => { setSearch(value); if (value.trim()) { setSelectedSet(""); setSelected(null); } }}
        onSelect={setSelected} onImport={() => setParticipantDialog("import")} onCreate={() => setParticipantDialog("create")} onPendingSetChange={setPendingSetId}
        onBeginResults={beginResultsEditing} onCancelResults={cancelResultsEditing}
        onConfirmResults={() => setParticipantAction("results")} onToggleRoute={toggleDraftRoute}
        onConfirmCheckIn={() => setParticipantAction("check-in")}
        canEdit={sectionPermissions.includes("participants.edit")} onEdit={setEditingParticipant}
        onReceptionAction={setParticipantAction} canManage={sectionPermissions.includes("participants.manage")}
      />
      </> : section === "exports" ? <ExportsSection token={token}/> : section === "applications" ? <ApplicationsSection token={token} onImported={() => load(true)}/> : section === "clubs" ? <ClubsSection token={token} stage={event?.stage} canMerge={sectionPermissions.includes("clubs.merge")} canManage={sectionPermissions.includes("participants.manage")} canEdit={sectionPermissions.includes("clubs.manage")} onParticipantsChanged={() => load(true)}/> : section === "qualification" ? <QualificationSection onOpenParticipant={(id) => { setSearch(""); setSelectedSet(""); setSelected(null); setRequestedParticipantId(id); setSection("participants"); setNavigationOpen(false); }} token={token} canExport={sectionPermissions.includes("exports.create")} onUpdated={() => load(true)}/> : section === "routes" ? <RoutesSection routes={event?.routes ?? []} token={token} onUpdated={load}/> : section === "categories" ? <CategoriesSection token={token} event={event} onChanged={() => load(true)}/> : section === "final" ? <FinalSection token={token} canResolveConflicts={sectionPermissions.includes("judge_conflicts.resolve")} canExport={sectionPermissions.includes("exports.create")} onUpdated={() => load(true)}/> : section === "backups" && sectionPermissions.includes("backups.manage") ? <BackupsSection token={token}/> : <SettingsSection routes={event?.routes ?? []} token={token} event={event} currentRole={currentUser?.role} permissions={[...sectionPermissions, ...(currentUser?.permissions.includes("users.presence") ? ["users.presence"] : [])]} onParticipantsChanged={() => load(true)}/>}
    </div>
    {editingParticipant && event && <ParticipantEditDialog token={token} participant={editingParticipant} event={event} canMerge={sectionPermissions.includes("participants.merge")} onClose={() => setEditingParticipant(null)} onSaved={(updated) => { setEditingParticipant(null); setSelected(updated); void load(true); }}/>}
    {setEditor && <SetEditorDialog state={setEditor} suggestedNumber={(event?.sets.length ?? 0) + 1} defaultDate={event?.starts_on ?? ""} saving={setsSaving} onClose={() => setSetEditor(null)} onSave={saveSet}/>}
    {setAction && <SetActionDialog state={setAction} saving={setsSaving} onClose={() => setSetAction(null)} onConfirm={applySetAction}/>} 
    {selected && participantAction === "results" && <ConfirmDialog title={`Сохранить результаты участника №${selected.start_number}?`} description="После подтверждения рейтинг и публичные результаты будут пересчитаны." confirmLabel="Сохранить результаты" busy={resultsSaving} onCancel={() => setParticipantAction(null)} onConfirm={() => void saveResults()}/>} 
    {selected && participantAction === "check-in" && <ConfirmDialog title={`Подтвердить прибытие участника №${selected.start_number}?`} description={`Прибытие участника ${selected.surname} ${selected.name} в «${activeSet?.name}» будет подтверждено.`} confirmLabel="Подтвердить прибытие" busy={participantActionSaving} onCancel={() => setParticipantAction(null)} onConfirm={() => void confirmEntry()}/>} 
    {selected && participantAction && !["results", "check-in"].includes(participantAction) && <ConfirmDialog title={receptionActionTitle[participantAction] ?? "Изменить статус?"} description={`Изменение будет записано для участника №${selected.start_number} ${selected.surname} ${selected.name}.`} confirmLabel="Подтвердить" busy={participantActionSaving} onCancel={() => setParticipantAction(null)} onConfirm={() => void changeReceptionStatus()}/>} 
    {selected && pendingSet && pendingSet.id !== selected.set_id && <ConfirmDialog title="Перенести участника?" description={<><strong>{selected.surname} {selected.name}</strong> будет переназначен из «{activeSet?.name}» в «{pendingSet.name}».</>} confirmLabel="Подтвердить перенос" onCancel={() => setPendingSetId("")} onConfirm={() => void changeSet(pendingSet.id)}><div className="transfer-summary"><span><small>Текущий сет</small><strong>{activeSet?.name}</strong></span><span><small>Новый сет</small><strong>{pendingSet.name}</strong></span><span><small>Загрузка</small><strong>{pendingSet.participant_count}/{pendingSet.capacity}</strong></span></div></ConfirmDialog>}
    {participantDialog === "import" && <ParticipantImportDialog token={token} onClose={() => setParticipantDialog(null)} onImported={() => load(true)} onNotice={setImportNotification}/>} 
    {participantDialog === "create" && event && <ParticipantCreateDialog token={token} event={event} onClose={() => setParticipantDialog(null)} onCreated={() => load(true)} onNotice={setImportNotification}/>} 
    {importNotification && <RouteToast notification={importNotification} onClose={() => setImportNotification(null)}/>} 
    {setNotification && <RouteToast notification={setNotification} onClose={() => setSetNotification(null)}/>} 
    {resultsNotification && <RouteToast notification={resultsNotification} onClose={() => setResultsNotification(null)}/>} 
    {showRoleGuide && currentUser && <RoleGuideDialog role={currentUser.role} onClose={() => setShowRoleGuide(false)}/>}
  </main></ReadOnlyScope>;
}
