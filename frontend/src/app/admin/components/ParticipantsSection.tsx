"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDownAZ, Check, CreditCard, EyeOff, Info, LockKeyhole, MoreVertical, Pencil, Search, Plus, Upload, UserCheck, Users } from "lucide-react";
import { deleteParticipant, type EventInfo, type Participant } from "@/lib/api";
import { Trash2 } from "lucide-react";
import { ResponsiveDetail } from "./ResponsiveDetail";
import { ConfirmDialog } from "./ConfirmDialog";
import { RouteToast, type RouteNotification } from "./RoutesSection";

type Props = {
  token: string;
  onDeleted: () => void;
  event: EventInfo | null;
  participants: Participant[];
  selected: Participant | null;
  openRequested?: boolean;
  search: string;
  error: string;
  isLocked: boolean;
  editingResults: boolean;
  resultsSaving: boolean;
  draftCompletedRoutes: Set<string>;
  activeSetName?: string;
  onSearchChange: (value: string) => void;
  onSelect: (participant: Participant | null) => void;
  onImport: () => void;
  onCreate: () => void;
  onPendingSetChange: (setId: string) => void;
  onBeginResults: () => void;
  onCancelResults: () => void;
  onConfirmResults: () => void;
  onToggleRoute: (routeId: string) => void;
  onConfirmCheckIn: () => void;
  onReceptionAction: (action: "cancel-check-in" | "pay" | "unpay" | "merch-issue" | "merch-unissue") => void;
  canManage: boolean;
  canEdit: boolean;
  onEdit: (participant: Participant) => void;
};

const alphabetCollator = new Intl.Collator("ru", { sensitivity: "base", numeric: true });

export function ParticipantsSection({
  token, onDeleted,
  event, participants, selected, openRequested, search, error, isLocked, editingResults, resultsSaving,
  draftCompletedRoutes, activeSetName, onSearchChange, onSelect, onImport, onCreate, onPendingSetChange,
  onBeginResults, onCancelResults, onConfirmResults, onToggleRoute, onConfirmCheckIn, onReceptionAction, canManage, canEdit, onEdit,
}: Props) {
  const [detailOpen, setDetailOpen] = useState(Boolean(openRequested));
  useEffect(() => { if (openRequested) setDetailOpen(true); }, [openRequested]);
  const routeCount = (count: number) => `${count} ${count % 100 >= 11 && count % 100 <= 14 ? "трасс" : count % 10 === 1 ? "трасса" : count % 10 >= 2 && count % 10 <= 4 ? "трассы" : "трасс"}`;
  const [hideCheckedIn, setHideCheckedIn] = useState(false);
  const [deleting, setDeleting] = useState<{ person: Participant; operationId: string } | null>(null);
  const [deletingBusy, setDeletingBusy] = useState(false);
  const [notice, setNotice] = useState<RouteNotification | null>(null);
  async function confirmDelete() {
    if (!deleting || deletingBusy) return;
    setDeletingBusy(true);
    try {
      await deleteParticipant(token, deleting.person, deleting.operationId);
      if (selected?.id === deleting.person.id) onSelect(null);
      setDeleting(null); onDeleted();
      setNotice({ type: "success", title: "Участник удалён из соревнования" });
    } catch (error) {
      setNotice({ type: "error", title: error instanceof Error ? error.message : "Не удалось удалить участника" });
    } finally { setDeletingBusy(false); }
  }
  const [sortAlphabetically, setSortAlphabetically] = useState(false);
  const [menuPersonId, setMenuPersonId] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuTrigger = useRef<HTMLButtonElement | null>(null);
  const menuPerson = participants.find((person) => person.id === menuPersonId);
  useEffect(() => {
    if (menuPersonId) {
      menuRef.current?.showPopover();
      menuRef.current?.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus();
    }
  }, [menuPersonId]);

  function closeMenu() {
    menuRef.current?.hidePopover();
    setMenuPersonId(null);
    menuTrigger.current?.focus();
  }

  function participantActions(person: Participant, inMenu = false) {
    const locked = event?.sets.find((set) => set.id === person.set_id)?.status === "confirmed";
    function run(action: () => void) {
      onSelect(person);
      if (inMenu) closeMenu();
      action();
    }
    return <>
      {canManage && <><button role={inMenu ? "menuitem" : undefined} disabled={locked && !person.checked_in_at} onClick={() => run(() => person.checked_in_at ? onReceptionAction("cancel-check-in") : onConfirmCheckIn())}><UserCheck size={15}/>{person.checked_in_at ? "Отменить прибытие" : "Подтвердить прибытие"}</button>
      <button role={inMenu ? "menuitem" : undefined} onClick={() => run(() => onReceptionAction(person.is_paid ? "unpay" : "pay"))}><CreditCard size={15}/>{person.is_paid ? "Отменить оплату" : "Отметить оплату"}</button></>}
      {canEdit && <button role={inMenu ? "menuitem" : undefined} className="participant-edit-button" disabled={event?.stage !== "preparation"} title={event?.stage === "preparation" ? "Исправить данные участника" : "Доступно после отката к этапу «Подготовка»"} onClick={() => run(() => onEdit(person))}><Pencil size={14}/>Редактировать</button>}
      {canManage && inMenu && <button role="menuitem" className="danger-menu-item" disabled={event?.stage !== "preparation"} title="Удаление доступно только на этапе подготовки" onClick={() => run(() => setDeleting({ person, operationId: crypto.randomUUID() }))}><Trash2 size={14}/>Удалить</button>}
    </>;
  }

  const resultsAvailable = Boolean(event?.qualification_started_at) && event?.stage === "qualification";
  const hiddenCheckedInCount = participants.filter((person) => Boolean(person.checked_in_at)).length;
  const filteredParticipants = hideCheckedIn ? participants.filter((person) => !person.checked_in_at) : participants;
  const visibleParticipants = sortAlphabetically ? [...filteredParticipants].sort((left, right) => {
    const nameResult = alphabetCollator.compare(
      `${left.surname} ${left.name} ${left.patronymic ?? ""}`,
      `${right.surname} ${right.name} ${right.patronymic ?? ""}`,
    );
    return nameResult || alphabetCollator.compare(String(left.start_number), String(right.start_number));
  }) : filteredParticipants;

  function toggleCheckedInVisibility() {
    const nextValue = !hideCheckedIn;
    setHideCheckedIn(nextValue);
    if (nextValue && selected?.checked_in_at) onSelect(null);
  }

  return <section className="participants-workspace">
    <header className="admin-section-hero"><div><h1>Участники</h1><p>{hideCheckedIn ? `${visibleParticipants.length} показано` : search.trim() ? `${participants.length} найдено по всему фестивалю` : `${participants.length} записей`}</p></div><span className="participant-toolbar-actions"><button className="secondary-button compact-action" disabled={Boolean(event?.final_started_at)} title="Добавить участника вручную" onClick={onCreate}><Plus size={20}/>Добавить</button><button className="import-button" disabled={Boolean(event?.final_started_at)} title="Импортировать CSV, XLSX или XLSM" onClick={onImport}><Upload size={15}/>Импорт</button></span></header>
    <div id="participant-quick-menu" ref={menuRef} popover="auto" role="menu" aria-label="Действия участника" className="participant-quick-menu" onToggle={(event) => { if (event.newState === "closed") setMenuPersonId(null); }} onKeyDown={(event) => {
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const items = [...event.currentTarget.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')];
      const index = items.indexOf(document.activeElement as HTMLButtonElement);
      const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
      items[next]?.focus();
    }}>{menuPerson && participantActions(menuPerson, true)}</div>
    <div className="participants-content-grid">
    <section className="participants-pane"><div className="pane-toolbar"><label className="search-box"><Search size={18}/><input data-view-action type="search" value={search} onChange={(event) => onSearchChange(event.target.value)} placeholder="Номер, имя или клуб" aria-label="Поиск по всем участникам фестиваля"/></label><div className="participant-list-controls"><button data-view-action className={hideCheckedIn ? "arrival-visibility-toggle active" : "arrival-visibility-toggle"} type="button" aria-pressed={hideCheckedIn} onClick={toggleCheckedInVisibility}><EyeOff size={16}/><span>{hideCheckedIn ? "Прибывшие скрыты" : "Скрыть прибывших"}</span><b>{hiddenCheckedInCount}</b><i aria-hidden="true"/></button><button data-view-action className={sortAlphabetically ? "alphabet-sort-toggle active" : "alphabet-sort-toggle"} type="button" aria-pressed={sortAlphabetically} onClick={() => setSortAlphabetically((value) => !value)}><ArrowDownAZ size={16}/><span>По алфавиту</span><i aria-hidden="true"/></button></div>{event?.final_started_at && <small className="final-lock-note">После запуска финала добавление участников закрыто.</small>}</div>{error && <div className="error-banner compact">{error}</div>}<div className="participant-list" onScroll={() => { if (menuPersonId) closeMenu(); }}>{visibleParticipants.map((person) => <div key={person.id} className={`participant-list-row${canManage || canEdit ? " has-actions" : ""}`}><button data-view-action className={["participant-row", selected?.id === person.id ? "selected" : "", person.checked_in_at ? "checked-in" : ""].filter(Boolean).join(" ")} aria-pressed={selected?.id === person.id} onClick={() => { onSelect(person); setDetailOpen(true); }}><span className="bib small-bib">{person.start_number}</span><span className="person-main"><strong>{person.surname} {person.name}</strong><small>{person.club} · {person.group_name}</small></span><span className="person-score">{person.checked_in_at ? <><strong>{person.points} <span>очков</span></strong><small>{routeCount(person.completed_count)}</small></> : <span className="waiting-mark">Не пришел</span>}</span></button>{(canManage || canEdit) && <button className="participant-menu-trigger" aria-label={`Действия участника №${person.start_number}`} aria-haspopup="menu" aria-expanded={menuPersonId === person.id} aria-controls="participant-quick-menu" onClick={(click) => {
      if (menuPersonId === person.id) { closeMenu(); return; }
      menuTrigger.current = click.currentTarget;
      const rect = click.currentTarget.getBoundingClientRect();
      if (menuRef.current) {
        menuRef.current.style.left = `${Math.max(8, Math.min(rect.right - 220, window.innerWidth - 228))}px`;
        menuRef.current.style.top = `${Math.max(8, Math.min(rect.bottom + 4, window.innerHeight - 200))}px`;
      }
      setMenuPersonId(person.id);
    }}><MoreVertical size={18}/></button>}</div>)}{visibleParticipants.length === 0 && <div className="participant-list-empty"><EyeOff size={24}/><strong>Прибывшие скрыты</strong><span>{hiddenCheckedInCount ? "Включите отображение, чтобы вернуть участников в список." : "В этом списке пока нет ожидающих участников."}</span></div>}</div></section>
    <ResponsiveDetail open={detailOpen && Boolean(selected)} onClose={() => setDetailOpen(false)} label="Карточка участника"><section className="participant-card">{selected ? <>
      <div className="relief-card-ribbon">Стартовый номер {selected.start_number}</div><div className="relief-card-body"><div className="card-head"><div><h2>{selected.surname} {selected.name}</h2><p>{selected.patronymic && <>{selected.patronymic} · </>}{selected.club}</p></div>{selected.checked_in_at ? <div className="live-score arrived"><strong>{selected.points} <small>очков</small></strong><span>Прибыл · {routeCount(selected.completed_count)}</span></div> : <span className="not-checked-in">Не пришел</span>}</div>
      <div className="participant-status-strip"><span className="status-pill neutral">{selected.application_type === "collective" ? "Коллективная заявка" : "Индивидуальная заявка"}</span><span className={`status-pill ${selected.is_paid ? "success" : "danger"}`}>{selected.is_paid ? "Оплачено" : "Не оплачено"}</span><span className="status-pill neutral">{selected.merch_size ? `Футболка ${selected.merch_size}` : "Футболка не заказана"}</span></div>
      <div className="participant-reception-actions">{participantActions(selected)}</div>

      <div className="participant-fields"><div><span>Группа</span><strong>{selected.group_name}</strong></div><div><span>Год рождения</span><strong>{selected.birth_year}</strong></div><div><span>Разряд</span><strong>{selected.sport_rank}</strong></div><div><span>Клуб</span><strong>{selected.club}</strong></div><div className="wide"><span>Представитель</span><strong>{selected.representative || "Не указан"}</strong></div><label>Назначенный сет<select value={selected.set_id} onChange={(event) => onPendingSetChange(event.target.value)} disabled={isLocked || Boolean(selected.checked_in_at)}>{event?.sets.map((item) => <option key={item.id} value={item.id} disabled={(item.id !== selected.set_id && item.participant_count >= item.capacity) || item.status === "confirmed"}>{item.name} · {item.participant_count}/{item.capacity}</option>)}</select></label></div>
      {selected.checked_in_at ? <>
        <div className="routes-heading"><div><h3>Трассы</h3><p>{!resultsAvailable ? "Ввод результатов откроется после начала квалификации" : isLocked ? "Сет подтвержден, изменения заблокированы" : editingResults ? "Режим редактирования · изменения еще не сохранены" : "Режим просмотра · нажмите «Изменить», чтобы отметить трассы"}</p></div>
          <div className="results-edit-actions">{isLocked || !resultsAvailable ? <LockKeyhole size={18}/> : editingResults ? <><button className="secondary-button compact-action" disabled={resultsSaving} onClick={onCancelResults}>Отмена</button><button className="confirm-results-button" disabled={resultsSaving} onClick={onConfirmResults}><Check size={16}/>{resultsSaving ? "Сохраняем..." : "Подтвердить"}</button></> : <button className="edit-results-button" onClick={onBeginResults}><Pencil size={15}/>Изменить</button>}</div>
        </div>
        <div className={editingResults ? "route-grid editing" : "route-grid viewing"}>{event?.routes.filter((route) => route.is_active).map((route) => {
          const completed = editingResults ? draftCompletedRoutes.has(route.id) : selected.ascents.find((ascent) => ascent.route_id === route.id)?.completed ?? false;
          return <button key={route.id} disabled={!resultsAvailable || isLocked || !editingResults || resultsSaving} className={completed ? "route-toggle completed" : "route-toggle"} onClick={() => onToggleRoute(route.id)}><span className="check-box">{completed && <Check size={16}/>}</span><span className="route-toggle-copy"><strong className="route-toggle-number">{route.number}</strong><small className="route-toggle-meta"><span>{route.grade.replace(/[–—]/g, "/")}</span><span>{route.points} очков</span></small></span></button>;
        })}</div>
      </> : <div className="check-in-panel"><Info size={20}/><p>{isLocked ? "Сет подтверждён. Перенос участника недоступен." : `Участник назначен в ${activeSetName ?? "сет"}. Перенос доступен до подтверждения прибытия.`}</p></div>}
    </div></> : <div className="no-selection"><Users size={32}/><h2>Выберите участника</h2><p>Откройте карточку, чтобы подтвердить вход или отметить трассы.</p></div>}</section></ResponsiveDetail>
    </div>
    {deleting && <ConfirmDialog title="Удалить участника?" description={`Участник №${deleting.person.start_number} ${deleting.person.surname} ${deleting.person.name} ${deleting.person.patronymic ?? ""} будет удалён из текущего соревнования.`} confirmLabel="Удалить участника" danger safeDestructive busy={deletingBusy} confirmDisabled={event?.stage !== "preparation"} onCancel={() => setDeleting(null)} onConfirm={() => void confirmDelete()}/>}
    {notice && <RouteToast notification={notice} onClose={() => setNotice(null)}/>}
  </section>;
}
