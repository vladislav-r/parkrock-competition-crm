"use client";
import { SafetyExportDialog } from "./SafetyExportDialog";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Printer, ArrowDownUp, CreditCard, Info, Merge, MoreVertical, Pencil, Search, UserCheck, Users, X } from "lucide-react";
import { ApiError, Club, ClubMember, getClubs, ReceptionStatusUpdate, updateClub, updateClubReceptionBulk, updateParticipantReception } from "@/lib/api";
import { ClubMergeDialog } from "./ClubMergeDialog";
import { ResponsiveDetail } from "./ResponsiveDetail";
import { ConfirmDialog } from "./ConfirmDialog";
import { RouteToast, type RouteNotification } from "./RoutesSection";
import { deleteClub, type EventInfo } from "@/lib/api";
import { Trash2 } from "lucide-react";

type StatusField = keyof ReceptionStatusUpdate;
type PendingAction = { scope: "bulk"; field: StatusField; value: boolean } | { scope: "individual"; member: ClubMember; field: StatusField; value: boolean };
type SortKey = "start_number" | "full_name" | "set_name" | "application_type" | "checked_in" | "is_paid";

const STATUS_LABELS: Record<StatusField, [string, string]> = {
  checked_in: ["Подтвердить прибытие", "Отменить прибытие"], is_paid: ["Подтвердить оплату", "Отменить оплату"], merch_issued: ["Подтвердить выдачу мерча", "Отменить выдачу мерча"],
};

export function ClubsSection({ token, stage, canEdit, canMerge, canManage, canPrintSafety, onParticipantsChanged }: { token: string; stage?: EventInfo["stage"]; canPrintSafety: boolean; canEdit: boolean; canMerge: boolean; canManage: boolean; onParticipantsChanged: () => void }) {
  const [safetyTarget, setSafetyTarget] = useState<Club | "all" | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [clubs, setClubs] = useState<Club[]>([]);
  const [selectedClubId, setSelectedClubId] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [memberSearch, setMemberSearch] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; direction: "asc" | "desc" }>({ key: "start_number", direction: "asc" });
  const [editingClub, setEditingClub] = useState<Club | null>(null);
  const [deleting, setDeleting] = useState<{ club: Club; operationId: string } | null>(null);
  const [clubDraft, setClubDraft] = useState({ name: "", representative: "" });
  const [mergeSource, setMergeSource] = useState<Club | null>(null);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<RouteNotification | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await getClubs(token);
      setClubs(data);
      setSelectedClubId((current) => current && data.some((item) => item.id === current) ? current : (data[0]?.id ?? ""));
    } catch (error) { setNotice({ type: "error", title: error instanceof Error ? error.message : "Не удалось загрузить клубы" }); }
  }, [token]);
  useEffect(() => { void load(); const timer = window.setInterval(() => void load(), 3000); return () => window.clearInterval(timer); }, [load]);
  const club = clubs.find((item) => item.id === selectedClubId) ?? null;
  useEffect(() => { setSelectedIds(new Set(club?.members.filter((item) => item.application_type === "collective").map((item) => item.id) ?? [])); }, [selectedClubId]);
  const visibleClubs = useMemo(() => clubs.filter((item) => item.name.toLocaleLowerCase("ru").includes(search.trim().toLocaleLowerCase("ru"))), [clubs, search]);
  const selectedMembers = club?.members.filter((item) => selectedIds.has(item.id)) ?? [];
  const visibleMembers = useMemo(() => {
    const term = memberSearch.trim().toLocaleLowerCase("ru");
    const rows = (club?.members ?? []).filter((item) => !term || String(item.start_number).includes(term) || item.full_name.toLocaleLowerCase("ru").includes(term));
    const value = (item: ClubMember) => {
      if (sort.key === "checked_in" || sort.key === "is_paid") return Number(item[sort.key]);
      return item[sort.key];
    };
    return rows.sort((left, right) => {
      const a = value(left); const b = value(right);
      const compared = typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b), "ru", { numeric: true });
      return sort.direction === "asc" ? compared : -compared;
    });
  }, [club, memberSearch, sort]);
  const clubsRef = useRef<HTMLDivElement>(null);
  const membersRef = useRef<HTMLDivElement>(null);
  useEffect(() => { clubsRef.current?.scrollTo({ top: 0 }); }, [search]);
  useEffect(() => { membersRef.current?.scrollTo({ top: 0 }); }, [selectedClubId, memberSearch, sort]);

  function toggleMember(id: string) { setSelectedIds((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; }); }
  function changeSort(key: SortKey) { setSort((current) => current.key === key ? { key, direction: current.direction === "asc" ? "desc" : "asc" } : { key, direction: "asc" }); }
  function openClubEditor(item: Club) { setClubDraft({ name: item.name, representative: item.representative }); setEditingClub(item); }
  async function confirmDelete() {
    if (!deleting || saving) return;
    setSaving(true);
    try {
      const result = await deleteClub(token, deleting.club, deleting.operationId);
      setDeleting(null); await load(); onParticipantsChanged();
      setNotice({ type: "success", title: `Клуб удалён. Удалено участников: ${result.deleted_participants}` });
    } catch (error) {
      setNotice({ type: "error", title: error instanceof Error ? error.message : "Не удалось удалить клуб" });
    } finally { setSaving(false); }
  }
  async function saveClub() {
    if (!editingClub || !clubDraft.name.trim()) return;
    setSaving(true);
    try {
      const result = await updateClub(token, editingClub.id, clubDraft.name.trim(), clubDraft.representative.trim(), editingClub.version);
      setEditingClub(null); setSelectedClubId(result.id); await load(); onParticipantsChanged();
      setNotice({ type: "success", title: result.merged ? `Заявки объединены. Перенесено участников: ${result.updated_participants}` : `Клуб обновлён. Участников синхронизировано: ${result.updated_participants}` });
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) await load();
      setNotice({ type: "error", title: error instanceof Error ? error.message : "Не удалось обновить клуб" });
    } finally { setSaving(false); }
  }
  function queueBulk(field: StatusField, value: boolean) {
    if (!selectedMembers.length) { setNotice({ type: "error", title: "Выберите хотя бы одного участника" }); return; }
    if (field === "merch_issued" && value && !selectedMembers.some((item) => item.merch_size)) { setNotice({ type: "error", title: "Среди выбранных нет участников с заказанным мерчем" }); return; }
    setPending({ scope: "bulk", field, value });
  }
  const unpaidArrivalCount = pending?.field === "checked_in" && pending.value
    ? (pending.scope === "bulk" ? selectedMembers : [pending.member]).filter((member) => !member.is_paid).length : 0;
  async function applyAction() {
    if (!pending || !club) return;
    setSaving(true);
    try {
      const update = { [pending.field]: pending.value } as ReceptionStatusUpdate;
      if (pending.scope === "bulk") {
        const members = pending.field === "merch_issued" && pending.value ? selectedMembers.filter((item) => item.merch_size) : selectedMembers;
        const result = await updateClubReceptionBulk(token, club.id, members, update, unpaidArrivalCount > 0);
        setNotice({ type: "success", title: `Обновлено участников: ${result.updated}` });
      } else {
        await updateParticipantReception(token, pending.member.id, pending.member.version, update, unpaidArrivalCount > 0);
        setNotice({ type: "success", title: `Участник №${pending.member.start_number} обновлён` });
      }
      setPending(null); await load(); onParticipantsChanged();
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) await load();
      setNotice({ type: "error", title: error instanceof Error ? error.message : "Не удалось выполнить действие" });
    } finally { setSaving(false); }
  }

  const targetCount = pending?.scope === "bulk" ? (pending.field === "merch_issued" && pending.value ? selectedMembers.filter((item) => item.merch_size).length : selectedMembers.length) : 1;
  const actionLabel = pending ? STATUS_LABELS[pending.field][pending.value ? 0 : 1] : "";
  return <section className="clubs-workspace">
    <header className="admin-section-hero"><div><h1>Клубы</h1><p>{clubs.length} клубов · {clubs.reduce((sum, item) => sum + item.participant_count, 0)} участников</p></div>{canPrintSafety && <button className="secondary-button" onClick={() => setSafetyTarget("all")}><Printer size={16}/>Печать ТБ</button>}</header>
    <div className="clubs-content-grid">
    <aside className="clubs-list-pane"><div className="clubs-pane-head"><label className="search-box"><Search size={17}/><input data-view-action value={search} onChange={(event) => setSearch(event.target.value)} aria-label="Найти клуб" placeholder="Найти клуб"/>{search && <button data-view-action type="button" className="club-search-clear" aria-label="Очистить поиск клубов" title="Очистить поиск" onClick={(event) => { setSearch(""); event.currentTarget.parentElement?.querySelector("input")?.focus(); }}><X size={16}/></button>}</label></div><div className="clubs-list" ref={clubsRef}>{visibleClubs.map((item) => <div className={item.id === selectedClubId ? "club-list-entry active" : "club-list-entry"} key={item.id}><button data-view-action className={item.id === selectedClubId ? "club-list-item active" : "club-list-item"} onClick={() => { setSelectedClubId(item.id); setDetailOpen(true); }}><span><strong>{item.name}</strong><small>{item.representative || "Представитель не указан"}</small></span><b>{item.participant_count}</b></button>{(canMerge || canEdit || canPrintSafety) && <div className="club-menu"><button className="club-menu-trigger" aria-label={`Действия клуба ${item.name}`} popoverTarget={`club-menu-${item.id}`} onClick={(event) => {
      const rect = event.currentTarget.getBoundingClientRect();
      const popup = document.getElementById(`club-menu-${item.id}`);
      if (popup) { popup.style.left = `${Math.max(8, Math.min(rect.right - 170, window.innerWidth - 178))}px`; popup.style.top = `${Math.min(rect.bottom + 4, window.innerHeight - 210)}px`; }
    }}><MoreVertical size={18}/></button><div id={`club-menu-${item.id}`} popover="auto" className="club-menu-popup"><button disabled={!canEdit} onClick={(event) => { (event.currentTarget.parentElement as HTMLElement).hidePopover(); openClubEditor(item); }}><Pencil size={15}/>Редактировать клуб</button><button disabled={!canMerge} onClick={(event) => { (event.currentTarget.parentElement as HTMLElement).hidePopover(); setMergeSource(item); }}><Merge size={15}/>Объединить</button><button className="danger-menu-item" disabled={!canEdit || !canManage || stage !== "preparation"} title="Удаление доступно только на этапе подготовки" onClick={(event) => { (event.currentTarget.parentElement as HTMLElement).hidePopover(); setDeleting({ club: item, operationId: crypto.randomUUID() }); }}><Trash2 size={15}/>Удалить</button>{canPrintSafety && <button onClick={(event) => { (event.currentTarget.parentElement as HTMLElement).hidePopover(); setSafetyTarget(item); }}><Printer size={15}/>Печать ТБ</button>}</div></div>}</div>)}</div></aside>
    <ResponsiveDetail open={detailOpen && Boolean(club)} onClose={() => setDetailOpen(false)} label="Карточка клуба"><div className="club-detail-pane">{club ? <><div className="club-relief-body"><div className="club-detail-head"><div><h2>{club.name}</h2><p>Представитель: {club.representative || "не указан"}</p></div><div className="club-summary"><span><b>{club.checked_in_count}/{club.participant_count}</b><small>прибыли</small></span><span><b>{club.paid_count}/{club.participant_count}</b><small>оплатили</small></span></div></div>
      <div className="club-selection-toolbar"><div className="club-selection-note" title="Индивидуальных участников можно добавить вручную."><Info size={16}/><strong>Выбрано: {selectedMembers.length} · Коллективные заявки: {club.collective_count}</strong></div>{canEdit && <button className="edit-club-button" onClick={() => openClubEditor(club)}><Pencil size={14}/>Редактировать клуб</button>}</div>
      <div className="club-table-toolbar">
      {canManage && <div className="club-bulk-actions"><button className="reception-confirm" onClick={() => queueBulk("checked_in", true)}><UserCheck size={15}/>Подтвердить прибытие</button><button onClick={() => queueBulk("checked_in", false)}><X size={15}/>Отменить прибытие</button><button className="reception-confirm" onClick={() => queueBulk("is_paid", true)}><CreditCard size={15}/>Подтвердить оплату</button><button onClick={() => queueBulk("is_paid", false)}><X size={15}/>Отменить оплату</button></div>}
      <div className="club-member-search"><label className="search-box"><Search size={17}/><input data-view-action value={memberSearch} onChange={(event) => setMemberSearch(event.target.value)} aria-label="Поиск участников клуба" placeholder="Номер или ФИО участника"/>{memberSearch && <button data-view-action type="button" className="club-search-clear" aria-label="Очистить поиск участников клуба" title="Очистить поиск" onClick={(event) => { setMemberSearch(""); event.currentTarget.parentElement?.querySelector("input")?.focus(); }}><X size={16}/></button>}</label><span>{visibleMembers.length} из {club.members.length}</span></div>
      </div>
      <div className="club-members-table" ref={membersRef}><div className="club-member-row table-head"><label className="member-check"><input type="checkbox" aria-label="Выбрать всех показанных участников" checked={visibleMembers.length > 0 && visibleMembers.every((member) => selectedIds.has(member.id))} ref={(input) => { if (input) input.indeterminate = visibleMembers.some((member) => selectedIds.has(member.id)) && !visibleMembers.every((member) => selectedIds.has(member.id)); }} onChange={(event) => { const checked = event.target.checked; setSelectedIds((current) => { const next = new Set(current); visibleMembers.forEach((member) => checked ? next.add(member.id) : next.delete(member.id)); return next; }); }}/></label>{([["start_number", "№"], ["full_name", "ФИО"], ["set_name", "Сет"], ["application_type", "Заявка"], ["checked_in", "Прибытие"], ["is_paid", "Оплата"]] as Array<[SortKey, string]>).map(([key, label]) => <button data-view-action key={key} className={sort.key === key ? "active" : ""} onClick={() => changeSort(key)}>{label}<ArrowDownUp size={12}/></button>)}</div>{visibleMembers.map((member) => <div className="club-member-row" key={member.id}><label className="member-check"><input type="checkbox" aria-label={`Выбрать участника №${member.start_number}`} checked={selectedIds.has(member.id)} onChange={() => toggleMember(member.id)}/><span/></label><b className={member.checked_in ? "member-number bib checked-in" : "member-number bib"}>{member.start_number}</b><strong className="member-full-name">{member.full_name}</strong><span>{member.set_name}</span><span>{member.application_type === "collective" ? "Коллективная" : "Индивидуальная"}</span><button disabled={!canManage} className={member.checked_in ? "status-chip success" : "status-chip"} onClick={() => setPending({ scope: "individual", member, field: "checked_in", value: !member.checked_in })}>{member.checked_in ? "Прибыл" : "Не прибыл"}</button><button disabled={!canManage} className={member.is_paid ? "status-chip success" : "status-chip"} onClick={() => setPending({ scope: "individual", member, field: "is_paid", value: !member.is_paid })}>{member.is_paid ? "Оплачено" : "Не оплачено"}</button></div>)}</div>
    </div></> : <div className="no-selection"><Users size={32}/><h2>Клубов пока нет</h2><p>Они появятся автоматически из заявок участников.</p></div>}</div></ResponsiveDetail>
    </div>
    {safetyTarget && <SafetyExportDialog token={token} club={safetyTarget === "all" ? undefined : safetyTarget} onClose={() => setSafetyTarget(null)}/>}
    {pending && <ConfirmDialog title={unpaidArrivalCount ? "Подтвердить прибытие без оплаты?" : `${actionLabel}?`} description={unpaidArrivalCount ? `Среди выбранных участников не отмечена оплата у ${unpaidArrivalCount}. Вы уверены, что хотите подтвердить прибытие без оплаты? Статусы оплаты не изменятся.` : pending.scope === "bulk" ? `Статус будет изменён у ${targetCount} участников клуба «${club?.name}» одной операцией.` : `Изменить статус участника №${pending.member.start_number}: ${pending.member.full_name}.`} confirmLabel={unpaidArrivalCount ? "Подтвердить прибытие без оплаты" : actionLabel} busy={saving} onCancel={() => setPending(null)} onConfirm={() => void applyAction()}/>}
    {editingClub && <ConfirmDialog title="Редактировать клуб" description="Название и представитель обновятся у всех участников клуба." confirmLabel="Сохранить изменения" busy={saving} onCancel={() => setEditingClub(null)} onConfirm={() => void saveClub()}><div className="club-edit-form"><label>Название клуба<input value={clubDraft.name} maxLength={200} onChange={(event) => setClubDraft((value) => ({ ...value, name: event.target.value }))}/></label><label>Представитель<input value={clubDraft.representative} maxLength={200} placeholder="ФИО представителя" onChange={(event) => setClubDraft((value) => ({ ...value, representative: event.target.value }))}/></label></div></ConfirmDialog>}
    {mergeSource && <ClubMergeDialog token={token} source={mergeSource} clubs={clubs} onCancel={() => setMergeSource(null)} onMerged={(id, count) => { setMergeSource(null); setSelectedClubId(id); void load(); onParticipantsChanged(); setNotice({ type: "success", title: `Клубы объединены. Участников: ${count}. Резервная копия создана.` }); }}/>}
    {notice && <RouteToast notification={notice} onClose={() => setNotice(null)}/>} 
    {deleting && <ConfirmDialog title="Удалить клуб и всех его участников?" description={`Клуб «${deleting.club.name}» (${deleting.club.representative || "без представителя"}) будет удалён из справочника вместе со всеми участниками: ${deleting.club.participant_count}. Включая коллективные и индивидуальные заявки, независимо от выбранных строк.`} confirmLabel="Удалить клуб и участников" danger safeDestructive busy={saving} confirmDisabled={stage !== "preparation"} onCancel={() => setDeleting(null)} onConfirm={() => void confirmDelete()}/>}
  </section>;
}
