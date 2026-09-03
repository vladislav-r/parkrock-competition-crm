"use client";

import { useCallback, useEffect, useState } from "react";
import { Activity, BookOpen, Database, ExternalLink, Pencil, Plus, Save, ShieldCheck, Sparkles, Trash2, UserCog, X } from "lucide-react";
import { AuditEntry, clearParticipants, createUser, EventInfo, FinalRoute, getAudit, getRoleMatrix, getUserFinalRoutes, getUsers, RoleMatrix, Route, seedDemoFinalResults, seedDemoParticipants, seedDemoQualificationResults, StaffUser, updateRolePermissions, updateUser, UserRole } from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";
import { RouteToast, type RouteNotification } from "./RoutesSection";

const ROLE_LABELS: Record<UserRole, string> = { reception: "Ресепшен", secretary: "Секретарь", chief_judge: "Главный судья", administrator: "Администратор", route_judge: "Судья на трассе" };
const ACTION_LABELS: Record<string, string> = { "auth.login": "Вход", "auth.logout": "Выход", "authorization.denied": "Отказ в доступе", "request.failed": "Неуспешная операция", "user.create": "Создание пользователя", "user.update": "Изменение пользователя", "role.permissions.update": "Изменение прав", "participant.create": "Ручное добавление участника", "participant.import": "Импорт участников", "participant.clear": "Очистка участников", "participant.demo_seed": "Заполнение демо-участниками", "demo.qualification_results": "Заполнение демо-результатов квалификации", "demo.final_results": "Заполнение демо-результатов финала", "participant.results": "Изменение результатов", "participant.check-in": "Подтверждение прибытия", "participant.move": "Перенос участника", "categories.update": "Изменение категорий и медалей", "final.category-participation.update": "Изменение состава финала", "route.create": "Создание трассы", "route.update": "Изменение трассы", "set.confirm": "Подтверждение сета", "set.reopen": "Открытие сета", "backup.create": "Создание резервной копии", "backup.upload": "Загрузка резервной копии", "backup.verify": "Проверка резервной копии", "backup.restore": "Восстановление базы", "backup.delete": "Удаление резервной копии" };
const MONITORING_URL = process.env.NODE_ENV === "development" ? "http://127.0.0.1:3001/d/parkrock-performance" : "/monitoring/d/parkrock-performance";
type UserPayload = { email: string; full_name: string; password: string; role: UserRole; assigned_final_route_id: string | null };
type Pending = { type: "user"; user: StaffUser | null; payload: UserPayload } | { type: "toggle"; user: StaffUser } | { type: "permissions"; role: UserRole; permissions: string[] };
type DataAction = { type: "clear"; setId?: string; label: string; count: number } | { type: "seed" } | { type: "qualification-results" } | { type: "final-results" };

export function SettingsSection({ token, routes, event, currentRole, permissions: currentPermissions, onParticipantsChanged }: { token: string; routes: Route[]; event: EventInfo | null; currentRole?: UserRole; permissions: string[]; onParticipantsChanged: () => Promise<void> }) {
  const [tab, setTab] = useState<"users" | "roles" | "audit" | "data">(() => currentPermissions.includes("users.manage") ? "users" : currentPermissions.includes("roles.manage") ? "roles" : currentPermissions.includes("audit.view") ? "audit" : "data");
  const [users, setUsers] = useState<StaffUser[]>([]);
  const [finalRoutes, setFinalRoutes] = useState<FinalRoute[]>([]);
  const [matrix, setMatrix] = useState<RoleMatrix | null>(null);
  const [audit, setAudit] = useState<{ items: AuditEntry[]; total: number }>({ items: [], total: 0 });
  const [filters, setFilters] = useState({ action: "", actor: "", result: "" });
  const [editor, setEditor] = useState<StaffUser | "new" | null>(null);
  const [editorRole, setEditorRole] = useState<UserRole>("reception");
  const [selectedRole, setSelectedRole] = useState<UserRole>("reception");
  const [permissions, setPermissions] = useState<Set<string>>(new Set());
  const [pending, setPending] = useState<Pending | null>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<RouteNotification | null>(null);
  const [dataAction, setDataAction] = useState<DataAction | null>(null);
  const canUsers = currentPermissions.includes("users.manage");
  const canRoles = currentPermissions.includes("roles.manage");
  const canAudit = currentPermissions.includes("audit.view");

  const load = useCallback(async () => {
    try {
      const [userRows, routeRows, roleRows, auditRows] = await Promise.all([
        canUsers ? getUsers(token) : Promise.resolve([]),
        canUsers ? getUserFinalRoutes(token) : Promise.resolve([]),
        canRoles ? getRoleMatrix(token) : Promise.resolve(null),
        canAudit ? getAudit(token, filters) : Promise.resolve({ items: [], total: 0 }),
      ]);
      setUsers(userRows); setFinalRoutes(routeRows); setMatrix(roleRows); setAudit(auditRows);
    } catch (error) { setNotice({ type: "error", title: error instanceof Error ? error.message : "Не удалось загрузить настройки" }); }
  }, [token, filters, canUsers, canRoles, canAudit]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setPermissions(new Set(matrix?.roles.find((item) => item.role === selectedRole)?.permissions ?? [])); }, [matrix, selectedRole]);

  function prepareUser(formData: FormData) {
    const role = String(formData.get("role")) as UserRole;
    setPending({ type: "user", user: editor === "new" ? null : editor, payload: { email: String(formData.get("email")).trim(), full_name: String(formData.get("full_name")).trim(), password: String(formData.get("password")), role, assigned_final_route_id: role === "route_judge" ? String(formData.get("assigned_final_route_id") || "") || null : null } });
  }
  async function apply() {
    if (!pending) return; setSaving(true);
    try {
      if (pending.type === "user") {
        if (pending.user) {
          const payload: { expected_version: number; email: string; full_name: string; role: UserRole; assigned_final_route_id: string | null; password?: string } = { expected_version: pending.user.version, email: pending.payload.email, full_name: pending.payload.full_name, role: pending.payload.role, assigned_final_route_id: pending.payload.assigned_final_route_id };
          if (pending.payload.password) payload.password = pending.payload.password;
          await updateUser(token, pending.user.id, payload);
        } else await createUser(token, pending.payload);
        setEditor(null); setNotice({ type: "success", title: pending.user ? "Пользователь обновлён" : "Пользователь создан" });
      } else if (pending.type === "toggle") {
        await updateUser(token, pending.user.id, { expected_version: pending.user.version, is_active: !pending.user.is_active });
        setNotice({ type: "success", title: pending.user.is_active ? "Пользователь отключён" : "Пользователь включён" });
      } else {
        await updateRolePermissions(token, pending.role, pending.permissions);
        setNotice({ type: "success", title: `Права роли «${ROLE_LABELS[pending.role]}» сохранены` });
      }
      setPending(null); await load();
    } catch (error) { setNotice({ type: "error", title: error instanceof Error ? error.message : "Изменение не выполнено" }); setPending(null); }
    finally { setSaving(false); }
  }

  async function applyDataAction() {
    if (!dataAction) return;
    setSaving(true);
    try {
      if (dataAction.type === "clear") {
        const result = await clearParticipants(token, dataAction.setId);
        setNotice({ type: "success", title: `Удалено участников: ${result.deleted}` });
      } else if (dataAction.type === "seed") {
        const result = await seedDemoParticipants(token);
        setNotice({ type: "success", title: `Создано демо-участников: ${result.created}`, details: "По 20 человек в каждой возрастной группе, равномерно распределенных по сетам." });
      } else if (dataAction.type === "qualification-results") {
        const result = await seedDemoQualificationResults(token);
        setNotice({ type: "success", title: `Заполнены результаты квалификации: ${result.updated_participants} участников`, details: `Отмечено прохождений: ${result.completed_ascents}.` });
      } else {
        const result = await seedDemoFinalResults(token);
        setNotice({ type: "success", title: `Заполнены результаты финала: ${result.updated_finalists} финалистов`, details: `Настроено категорий: ${result.updated_categories}.` });
      }
      setDataAction(null); await onParticipantsChanged(); await load();
    } catch (error) { setNotice({ type: "error", title: error instanceof Error ? error.message : "Операция не выполнена" }); setDataAction(null); }
    finally { setSaving(false); }
  }

  return <section className="settings-pane"><div className="admin-workspace-container">
    <header className="settings-header admin-section-hero"><div><div className="eyebrow">Настройки</div><h1>Управление системой</h1><p>Учетные записи, разрешения, журнал и служебные данные фестиваля.</p></div>{currentRole === "administrator" && <div className="participant-toolbar-actions"><a className="secondary-button" href={MONITORING_URL} target="_blank" rel="noreferrer"><Activity size={17}/>Мониторинг<ExternalLink size={14}/></a></div>}</header>
    <nav className="settings-tabs">{canUsers && <button className={tab === "users" ? "active" : ""} onClick={() => setTab("users")}><UserCog size={17}/>Пользователи</button>}{canRoles && <button className={tab === "roles" ? "active" : ""} onClick={() => setTab("roles")}><ShieldCheck size={17}/>Права ролей</button>}{canAudit && <button className={tab === "audit" ? "active" : ""} onClick={() => setTab("audit")}><BookOpen size={17}/>Журнал</button>}{currentRole === "administrator" && <button className={tab === "data" ? "active" : ""} onClick={() => setTab("data")}><Database size={17}/>Демо-данные</button>}</nav>
    {tab === "users" && canUsers && <div className="settings-card"><div className="settings-card-head"><div><h2>Учетные записи</h2><p>{users.length} сотрудников</p></div><button className="primary-action" onClick={() => { setEditorRole("reception"); setEditor("new"); }}><Plus size={16}/>Добавить</button></div><div className="users-table"><div className="users-head"><span>Сотрудник</span><span>Роль</span><span>Трасса</span><span>Статус</span><span/></div>{users.map((user) => <div className={!user.is_active ? "user-row inactive" : "user-row"} key={user.id}><span><strong>{user.full_name}</strong><small>{user.email}</small></span><span>{ROLE_LABELS[user.role]}</span><span>{user.assigned_final_route_id ? `№ ${finalRoutes.find((route) => route.id === user.assigned_final_route_id)?.number ?? "—"}` : "—"}</span><button className={user.is_active ? "user-status active" : "user-status"} onClick={() => setPending({ type: "toggle", user })}>{user.is_active ? "Активен" : "Отключён"}</button><button className="icon-button" title="Редактировать" onClick={() => { setEditorRole(user.role); setEditor(user); }}><Pencil size={16}/></button></div>)}</div></div>}
    {tab === "roles" && matrix && <div className="settings-card role-matrix"><div className="role-list">{matrix.roles.map((item) => <button key={item.role} className={selectedRole === item.role ? "active" : ""} onClick={() => setSelectedRole(item.role)}><strong>{ROLE_LABELS[item.role]}</strong><small>{item.permissions.length} разрешений</small></button>)}</div><div className="permission-list"><h2>{ROLE_LABELS[selectedRole]}</h2><p>{selectedRole === "administrator" ? "Права администратора защищены." : "Каждое разрешение проверяется сервером."}</p>{Object.entries(matrix.available_permissions).map(([permission, label]) => <label key={permission}><input type="checkbox" checked={permissions.has(permission)} disabled={selectedRole === "administrator"} onChange={(event) => setPermissions((current) => { const next = new Set(current); event.target.checked ? next.add(permission) : next.delete(permission); return next; })}/><span>{label}<small>{permission}</small></span></label>)}<button className="save-route-button" disabled={selectedRole === "administrator"} onClick={() => setPending({ type: "permissions", role: selectedRole, permissions: Array.from(permissions) })}><Save size={16}/>Сохранить права</button></div></div>}
    {tab === "audit" && <div className="settings-card"><div className="settings-card-head"><div><h2>Журнал действий</h2><p>{audit.total} записей · только чтение</p></div></div><form className="audit-filters" onSubmit={(event) => { event.preventDefault(); const data = new FormData(event.currentTarget); setFilters({ actor: String(data.get("actor")), action: String(data.get("action")), result: String(data.get("result")) }); }}><input name="actor" placeholder="Почта сотрудника"/><input name="action" placeholder="Код действия"/><select name="result"><option value="">Все результаты</option><option value="success">Успешно</option><option value="denied">Отказано</option><option value="error">Ошибка</option></select><button className="secondary-button">Применить</button></form><div className="audit-table"><div className="audit-head"><span>Время</span><span>Сотрудник</span><span>Действие</span><span>Объект и подробности</span><span>Результат</span></div>{audit.items.map((entry) => <div className="audit-row" key={entry.id}><span>{new Date(entry.created_at).toLocaleString("ru-RU")}</span><span><strong>{entry.actor_name || entry.actor_email || "Система"}</strong><small>{[entry.actor_email, ROLE_LABELS[entry.actor_role as UserRole] ?? entry.actor_role].filter(Boolean).join(" · ")}</small></span><span>{ACTION_LABELS[entry.action] ?? entry.action}</span><span><strong>{entry.target_label || "Данные"}</strong>{entry.details && <small>{entry.details}</small>}</span><span className={`audit-result ${entry.result}`}>{entry.result === "success" ? "Успешно" : entry.result === "denied" ? "Отказано" : "Ошибка"}</span></div>)}</div></div>}
    {tab === "data" && currentRole === "administrator" && event && <div className="demo-data-grid"><div className="settings-card"><div className="settings-card-head"><div><h2>Очистка участников</h2><p>Удаляются участники выбранного сета вместе с результатами. Записи журнала сохраняются.</p></div></div><div className="demo-set-list">{event.sets.map((item) => <div key={item.id}><span><strong>{item.name}</strong><small>{item.participant_count} участников</small></span><button className="danger-outline-button" disabled={item.participant_count === 0} onClick={() => setDataAction({ type: "clear", setId: item.id, label: item.name, count: item.participant_count })}><Trash2 size={15}/>Очистить</button></div>)}</div><button className="danger-action-button" disabled={event.participant_count === 0} onClick={() => setDataAction({ type: "clear", label: "все сеты", count: event.participant_count })}><Trash2 size={16}/>Очистить всех участников во всех сетах</button></div><div className="demo-actions-column"><div className="settings-card demo-seed-card"><div className="dialog-icon"><Sparkles size={22}/></div><h2>Заполнить демо-участниками</h2><p>Создаст по 20 вымышленных участников в каждой возрастной группе и равномерно распределит их по сетам. Подтвержденные сеты будут открыты для работы.</p><div className="demo-total"><strong>{event.participant_count}</strong><span>участников сейчас</span></div><button className="primary-action" disabled={event.participant_count > 0} onClick={() => setDataAction({ type: "seed" })}><Sparkles size={16}/>Создать демо-данные</button>{event.participant_count > 0 && <small>Сначала очистите участников во всех сетах.</small>}</div><div className="settings-card demo-results-card"><div className="dialog-icon"><Sparkles size={22}/></div><h2>Заполнить демо-результаты</h2><p>Результаты каждой стадии заполняются отдельно и заменяют прежние демо-результаты этой стадии.</p><button className="secondary-button" disabled={event.stage !== "qualification" || event.participant_count === 0} onClick={() => setDataAction({ type: "qualification-results" })}><Sparkles size={15}/>Заполнить квалификацию</button><button className="secondary-button" disabled={event.stage !== "final"} onClick={() => setDataAction({ type: "final-results" })}><Sparkles size={15}/>Заполнить финал</button><small>{event.stage === "qualification" ? "Сейчас доступна квалификация." : event.stage === "final" ? "Сейчас доступен финал." : "Фестиваль завершён."}</small></div></div></div>}
    {editor && <div className="modal-backdrop" onMouseDown={() => setEditor(null)}><form action={prepareUser} className="user-editor" onMouseDown={(event) => event.stopPropagation()}><button type="button" className="dialog-close" onClick={() => setEditor(null)}><X size={18}/></button><div className="eyebrow">Учетная запись</div><h2>{editor === "new" ? "Новый пользователь" : "Редактирование"}</h2><label>ФИО<input name="full_name" defaultValue={editor === "new" ? "" : editor.full_name} minLength={2} required/></label><label>Почта<input name="email" type="text" inputMode="email" autoCapitalize="none" autoCorrect="off" spellCheck={false} placeholder="name@example.com" defaultValue={editor === "new" ? "" : editor.email} required/><small>Адрес проверяется после удаления случайных пробелов.</small></label><label>{editor === "new" ? "Пароль" : "Новый пароль (необязательно)"}<input name="password" type="password" minLength={8} required={editor === "new"}/><small>Не менее 8 символов.</small></label><label>Роль<select name="role" value={editorRole} onChange={(event) => setEditorRole(event.target.value as UserRole)}>{Object.entries(ROLE_LABELS).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>{editorRole === "route_judge" && <label>Финальная трасса судьи<select name="assigned_final_route_id" defaultValue={editor === "new" ? "" : editor.assigned_final_route_id ?? ""} required><option value="">Выберите трассу</option>{finalRoutes.map((route) => <option value={route.id} key={route.id}>Трасса №{route.number}</option>)}</select><small>Судья сможет сохранять результаты только на этой трассе.</small></label>}<button className="primary-button">Продолжить</button></form></div>}
    {pending && <ConfirmDialog title={pending.type === "permissions" ? "Сохранить права роли?" : pending.type === "toggle" ? `${pending.user.is_active ? "Отключить" : "Включить"} пользователя?` : pending.user ? "Сохранить пользователя?" : "Создать пользователя?"} description="Изменение вступит в силу сразу и будет записано в журнал." confirmLabel="Подтвердить" busy={saving} onCancel={() => setPending(null)} onConfirm={() => void apply()}/>} 
    {dataAction && <ConfirmDialog title={dataAction.type === "seed" ? "Создать демо-участников?" : dataAction.type === "qualification-results" ? "Заполнить квалификационные результаты?" : dataAction.type === "final-results" ? "Заполнить финальные результаты?" : `Очистить ${dataAction.label}?`} description={dataAction.type === "seed" ? "Демо-данные будут созданы только в пустом списке: по 20 человек в каждой возрастной группе с равномерным распределением по сетам." : dataAction.type === "qualification-results" ? "Текущие результаты квалификации у всех участников будут заменены случайными демонстрационными прохождениями." : dataAction.type === "final-results" ? "Текущие финальные попытки и результаты будут заменены случайными демонстрационными данными. Для участвующих категорий автоматически назначатся четыре трассы." : `Будет безвозвратно удалено участников: ${dataAction.count}. Связанные результаты также удалятся, а запись об операции останется в журнале.`} confirmLabel={dataAction.type === "seed" ? "Создать демо-данные" : dataAction.type === "qualification-results" ? "Заполнить квалификацию" : dataAction.type === "final-results" ? "Заполнить финал" : "Удалить участников"} danger={dataAction.type !== "seed"} busy={saving} onCancel={() => setDataAction(null)} onConfirm={() => void applyDataAction()}/>} 
    {notice && <RouteToast notification={notice} onClose={() => setNotice(null)}/>} 
  </div></section>;
}
