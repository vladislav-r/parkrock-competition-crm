"use client";

import { useState } from "react";
import { ArrowDownAZ, Check, CreditCard, EyeOff, LockKeyhole, PackageCheck, Pencil, Search, Upload, UserCheck, UserPlus, Users } from "lucide-react";
import type { EventInfo, Participant } from "@/lib/api";

type Props = {
  event: EventInfo | null;
  participants: Participant[];
  selected: Participant | null;
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
};

const alphabetCollator = new Intl.Collator("ru", { sensitivity: "base", numeric: true });

export function ParticipantsSection({
  event, participants, selected, search, error, isLocked, editingResults, resultsSaving,
  draftCompletedRoutes, activeSetName, onSearchChange, onSelect, onImport, onCreate, onPendingSetChange,
  onBeginResults, onCancelResults, onConfirmResults, onToggleRoute, onConfirmCheckIn, onReceptionAction, canManage,
}: Props) {
  const [hideCheckedIn, setHideCheckedIn] = useState(false);
  const [sortAlphabetically, setSortAlphabetically] = useState(false);
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
    <header className="admin-section-hero"><div><div className="eyebrow">Работа с фестивалем</div><h1>Участники</h1><p>{hideCheckedIn ? `${visibleParticipants.length} показано` : search.trim() ? `${participants.length} найдено по всему фестивалю` : `${participants.length} записей`}</p></div><span className="participant-toolbar-actions"><button className="secondary-button compact-action" disabled={Boolean(event?.final_started_at)} title="Добавить участника вручную" onClick={onCreate}><UserPlus size={15}/>Добавить</button><button className="import-button" disabled={Boolean(event?.final_started_at)} title="Импортировать CSV или XLSX" onClick={onImport}><Upload size={15}/>Импорт</button></span></header>
    <div className="participants-content-grid">
    <section className="participants-pane"><div className="pane-toolbar"><label className="search-box"><Search size={18}/><input type="search" value={search} onChange={(event) => onSearchChange(event.target.value)} placeholder="По всему фестивалю: стартовый номер, фамилия, имя или клуб" aria-label="Поиск по всем участникам фестиваля"/></label><div className="participant-list-controls"><button className={hideCheckedIn ? "arrival-visibility-toggle active" : "arrival-visibility-toggle"} type="button" aria-pressed={hideCheckedIn} onClick={toggleCheckedInVisibility}><EyeOff size={16}/><span>{hideCheckedIn ? "Прибывшие скрыты" : "Скрыть прибывших"}</span><b>{hiddenCheckedInCount}</b><i aria-hidden="true"/></button><button className={sortAlphabetically ? "alphabet-sort-toggle active" : "alphabet-sort-toggle"} type="button" aria-pressed={sortAlphabetically} onClick={() => setSortAlphabetically((value) => !value)}><ArrowDownAZ size={16}/><span>{sortAlphabetically ? "Сортировка по алфавиту" : "Сортировать по алфавиту"}</span><i aria-hidden="true"/></button></div>{event?.final_started_at && <small className="final-lock-note">После запуска финала добавление участников закрыто.</small>}</div>{error && <div className="error-banner compact">{error}</div>}<div className="participant-list">{visibleParticipants.map((person) => <button key={person.id} className={["participant-row", selected?.id === person.id ? "selected" : "", person.checked_in_at ? "checked-in" : ""].filter(Boolean).join(" ")} onClick={() => onSelect(person)}><span className="bib small-bib">{person.start_number}</span><span className="person-main"><strong>{person.surname} {person.name}</strong><small>{person.club} · {person.group_name}</small></span><span className="person-score">{person.checked_in_at ? <><strong>{person.completed_count}</strong><small>{person.points} очков</small></> : <span className="waiting-mark">Не пришел</span>}</span></button>)}{visibleParticipants.length === 0 && <div className="participant-list-empty"><EyeOff size={24}/><strong>Прибывшие скрыты</strong><span>{hiddenCheckedInCount ? "Включите отображение, чтобы вернуть участников в список." : "В этом списке пока нет ожидающих участников."}</span></div>}</div></section>
    <section className="participant-card">{selected ? <>
      <div className="card-head"><div><div className="eyebrow">Стартовый номер {selected.start_number}</div><h2>{selected.surname} {selected.name}</h2><p>{selected.patronymic}</p></div>{selected.checked_in_at ? <div className="live-score arrived"><strong>{selected.completed_count}</strong><span>Прибыл · {selected.points} очков</span></div> : <span className="not-checked-in">Не пришел</span>}</div>
      <div className="participant-status-strip"><span className="status-pill neutral">{selected.application_type === "collective" ? "Коллективная заявка" : "Индивидуальная заявка"}</span><span className={`status-pill ${selected.is_paid ? "success" : "danger"}`}>{selected.is_paid ? "Оплачено" : "Не оплачено"}</span><span className="status-pill neutral">{selected.merch_size ? `Футболка ${selected.merch_size}` : "Футболка не заказана"}</span><span className={`status-pill ${!selected.merch_size ? "muted" : selected.merch_issued ? "success" : "danger"}`}>{!selected.merch_size ? "Выдача не требуется" : selected.merch_issued ? "Мерч выдан" : "Мерч не выдан"}</span></div>
      {canManage && <div className="participant-reception-actions"><button onClick={() => selected.checked_in_at ? onReceptionAction("cancel-check-in") : onConfirmCheckIn()}><UserCheck size={15}/>{selected.checked_in_at ? "Отменить прибытие" : "Подтвердить прибытие"}</button><button onClick={() => onReceptionAction(selected.is_paid ? "unpay" : "pay")}><CreditCard size={15}/>{selected.is_paid ? "Отменить оплату" : "Отметить оплату"}</button><button disabled={!selected.merch_size} onClick={() => onReceptionAction(selected.merch_issued ? "merch-unissue" : "merch-issue")}><PackageCheck size={15}/>{selected.merch_issued ? "Отменить выдачу" : "Выдать мерч"}</button></div>}
      <div className="participant-fields"><div><span>Группа</span><strong>{selected.group_name}</strong></div><div><span>Год рождения</span><strong>{selected.birth_year}</strong></div><div><span>Разряд</span><strong>{selected.sport_rank}</strong></div><div><span>Клуб</span><strong>{selected.club}</strong></div><div className="wide"><span>Представитель</span><strong>{selected.representative || "Не указан"}</strong></div><label>Назначенный сет<select value={selected.set_id} onChange={(event) => onPendingSetChange(event.target.value)} disabled={isLocked || Boolean(selected.checked_in_at)}>{event?.sets.map((item) => <option key={item.id} value={item.id} disabled={(item.id !== selected.set_id && item.participant_count >= item.capacity) || item.status === "confirmed"}>{item.name} · {item.participant_count}/{item.capacity}</option>)}</select></label></div>
      {selected.checked_in_at ? <>
        <div className="routes-heading"><div><h3>Трассы</h3><p>{isLocked ? "Сет подтвержден, изменения заблокированы" : editingResults ? "Режим редактирования · изменения еще не сохранены" : "Режим просмотра · нажмите «Изменить», чтобы отметить трассы"}</p></div>
          <div className="results-edit-actions">{isLocked ? <LockKeyhole size={18}/> : editingResults ? <><button className="secondary-button compact-action" disabled={resultsSaving} onClick={onCancelResults}>Отмена</button><button className="confirm-results-button" disabled={resultsSaving} onClick={onConfirmResults}><Check size={16}/>{resultsSaving ? "Сохраняем..." : "Подтвердить"}</button></> : <button className="edit-results-button" onClick={onBeginResults}><Pencil size={15}/>Изменить</button>}</div>
        </div>
        <div className={editingResults ? "route-grid editing" : "route-grid viewing"}>{event?.routes.filter((route) => route.is_active).map((route) => {
          const completed = editingResults ? draftCompletedRoutes.has(route.id) : selected.ascents.find((ascent) => ascent.route_id === route.id)?.completed ?? false;
          return <button key={route.id} disabled={isLocked || !editingResults || resultsSaving} className={completed ? "route-toggle completed" : "route-toggle"} onClick={() => onToggleRoute(route.id)}><span className="check-box">{completed && <Check size={16}/>}</span><span><strong>№ {route.number} · {route.grade}</strong><small>{route.points} очков</small></span></button>;
        })}</div>
      </> : <div className="check-in-panel"><div><UserPlus size={22}/><div><strong>Участник назначен в {activeSetName}</strong><p>Подтвердите фактическое прибытие участника на фестиваль.</p></div></div>{canManage && <button className="check-in-button" disabled={isLocked} onClick={onConfirmCheckIn}><UserPlus size={17}/>Подтвердить прибытие</button>}</div>}
    </> : <div className="no-selection"><Users size={32}/><h2>Выберите участника</h2><p>Откройте карточку, чтобы подтвердить вход или отметить трассы.</p></div>}</section>
    </div>
  </section>;
}
