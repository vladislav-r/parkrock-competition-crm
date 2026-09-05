"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowDownUp, Check, CreditCard, PackageCheck, Pencil, Search, UserCheck, Users } from "lucide-react";
import { ApiError, Club, ClubMember, getClubs, ReceptionStatusUpdate, updateClub, updateClubReceptionBulk, updateParticipantReception } from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";
import { RouteToast, type RouteNotification } from "./RoutesSection";

type StatusField = keyof ReceptionStatusUpdate;
type PendingAction = { scope: "bulk"; field: StatusField; value: boolean } | { scope: "individual"; member: ClubMember; field: StatusField; value: boolean };
type SortKey = "start_number" | "full_name" | "set_name" | "application_type" | "checked_in" | "is_paid" | "merch";
type MergeTarget = { id: string; name: string; representative: string; participant_count: number };

const STATUS_LABELS: Record<StatusField, [string, string]> = {
  checked_in: ["Подтвердить прибытие", "Отменить прибытие"], is_paid: ["Подтвердить оплату", "Отменить оплату"], merch_issued: ["Подтвердить выдачу мерча", "Отменить выдачу мерча"],
};

export function ClubsSection({ token, canEdit, onParticipantsChanged }: { token: string; canEdit: boolean; onParticipantsChanged: () => void }) {
  const [clubs, setClubs] = useState<Club[]>([]);
  const [selectedClubId, setSelectedClubId] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [memberSearch, setMemberSearch] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; direction: "asc" | "desc" }>({ key: "start_number", direction: "asc" });
  const [editingClub, setEditingClub] = useState(false);
  const [clubDraft, setClubDraft] = useState({ name: "", representative: "" });
  const [mergeTarget, setMergeTarget] = useState<MergeTarget | null>(null);
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
      if (sort.key === "merch") return `${item.merch_size ?? ""}-${Number(item.merch_issued)}`;
      if (sort.key === "checked_in" || sort.key === "is_paid") return Number(item[sort.key]);
      return item[sort.key];
    };
    return rows.sort((left, right) => {
      const a = value(left); const b = value(right);
      const compared = typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b), "ru", { numeric: true });
      return sort.direction === "asc" ? compared : -compared;
    });
  }, [club, memberSearch, sort]);

  function toggleMember(id: string) { setSelectedIds((current) => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; }); }
  function changeSort(key: SortKey) { setSort((current) => current.key === key ? { key, direction: current.direction === "asc" ? "desc" : "asc" } : { key, direction: "asc" }); }
  function openClubEditor() { if (!club) return; setClubDraft({ name: club.name, representative: club.representative }); setEditingClub(true); }
  async function saveClub(mergeDuplicate = false) {
    if (!club || !clubDraft.name.trim()) return;
    setSaving(true);
    try {
      const result = await updateClub(token, club.id, clubDraft.name.trim(), clubDraft.representative.trim(), club.version, mergeDuplicate);
      setEditingClub(false); setMergeTarget(null); setSelectedClubId(result.id); await load(); onParticipantsChanged();
      setNotice({ type: "success", title: result.merged ? `Заявки объединены. Перенесено участников: ${result.updated_participants}` : `Клуб обновлён. Участников синхронизировано: ${result.updated_participants}` });
    } catch (error) {
      const detail = error instanceof ApiError && typeof error.detail === "object" && error.detail !== null ? error.detail as { code?: string; target_club?: MergeTarget } : null;
      if (!mergeDuplicate && error instanceof ApiError && error.status === 409 && detail?.code === "duplicate_club" && detail.target_club) {
        setEditingClub(false); setMergeTarget(detail.target_club); return;
      }
      if (error instanceof ApiError && error.status === 409) await load();
      setNotice({ type: "error", title: error instanceof Error ? error.message : "Не удалось обновить клуб" });
    } finally { setSaving(false); }
  }
  function queueBulk(field: StatusField, value: boolean) {
    if (!selectedMembers.length) { setNotice({ type: "error", title: "Выберите хотя бы одного участника" }); return; }
    if (field === "merch_issued" && value && !selectedMembers.some((item) => item.merch_size)) { setNotice({ type: "error", title: "Среди выбранных нет участников с заказанным мерчем" }); return; }
    setPending({ scope: "bulk", field, value });
  }
  async function applyAction() {
    if (!pending || !club) return;
    setSaving(true);
    try {
      const update = { [pending.field]: pending.value } as ReceptionStatusUpdate;
      if (pending.scope === "bulk") {
        const members = pending.field === "merch_issued" && pending.value ? selectedMembers.filter((item) => item.merch_size) : selectedMembers;
        const result = await updateClubReceptionBulk(token, club.id, members, update);
        setNotice({ type: "success", title: `Обновлено участников: ${result.updated}` });
      } else {
        await updateParticipantReception(token, pending.member.id, pending.member.version, update);
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
    <header className="admin-section-hero"><div><div className="eyebrow">Работа с фестивалем</div><h1>Клубы</h1><p>{clubs.length} клубов · {clubs.reduce((sum, item) => sum + item.participant_count, 0)} участников</p></div><div className="section-health"><Users size={22}/><span><strong>{clubs.length}</strong><small>клубов в системе</small></span></div></header>
    <div className="clubs-content-grid">
    <aside className="clubs-list-pane"><div className="clubs-pane-head"><label className="search-box"><Search size={17}/><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Найти клуб"/></label></div><div className="clubs-list">{visibleClubs.map((item) => <button key={item.id} className={item.id === selectedClubId ? "club-list-item active" : "club-list-item"} onClick={() => setSelectedClubId(item.id)}><span><strong>{item.name}</strong><small>{item.representative || "Представитель не указан"}</small></span><b>{item.participant_count}</b></button>)}</div></aside>
    <div className="club-detail-pane">{club ? <><div className="club-detail-head"><div><span className="eyebrow">Клуб</span><h2>{club.name}</h2><p>Представитель: {club.representative || "не указан"}</p>{canEdit && <button className="edit-club-button" onClick={openClubEditor}><Pencil size={14}/>Редактировать клуб</button>}</div><div className="club-summary"><span><b>{club.checked_in_count}/{club.participant_count}</b><small>прибыли</small></span><span><b>{club.paid_count}/{club.participant_count}</b><small>оплатили</small></span><span><b>{club.merch_issued_count}</b><small>мерч выдан</small></span></div></div>
      <div className="club-selection-note"><Check size={16}/><span>Автоматически выбраны коллективные заявки: {club.collective_count}. Индивидуальные можно добавить вручную.</span><strong>Выбрано: {selectedIds.size}</strong></div>
      <div className="club-bulk-actions"><span>Массово:</span><button onClick={() => queueBulk("checked_in", true)}><UserCheck size={15}/>Прибыли</button><button onClick={() => queueBulk("checked_in", false)}>Отменить прибытие</button><button onClick={() => queueBulk("is_paid", true)}><CreditCard size={15}/>Оплачено</button><button onClick={() => queueBulk("is_paid", false)}>Отменить оплату</button><button disabled title="Выдача мерча отключена для этого фестиваля"><PackageCheck size={15}/>Мерч отключён</button></div>
      <div className="club-member-search"><label className="search-box"><Search size={17}/><input value={memberSearch} onChange={(event) => setMemberSearch(event.target.value)} placeholder="Номер или ФИО участника"/></label><span>{visibleMembers.length} из {club.members.length}</span></div>
      <div className="club-members-table"><div className="club-member-row table-head"><span></span>{([["start_number", "№"], ["full_name", "ФИО"], ["set_name", "Сет"], ["application_type", "Заявка"], ["checked_in", "Прибытие"], ["is_paid", "Оплата"], ["merch", "Мерч"]] as Array<[SortKey, string]>).map(([key, label]) => <button key={key} className={sort.key === key ? "active" : ""} onClick={() => changeSort(key)}>{label}<ArrowDownUp size={12}/></button>)}</div>{visibleMembers.map((member) => <div className="club-member-row" key={member.id}><label className="member-check"><input type="checkbox" checked={selectedIds.has(member.id)} onChange={() => toggleMember(member.id)}/><span/></label><b className="member-number">№{member.start_number}</b><strong className="member-full-name">{member.full_name}</strong><span>{member.set_name}</span><span>{member.application_type === "collective" ? "Коллективная" : "Индивидуальная"}</span><button className={member.checked_in ? "status-chip success" : "status-chip"} onClick={() => setPending({ scope: "individual", member, field: "checked_in", value: !member.checked_in })}>{member.checked_in ? "Прибыл" : "Не прибыл"}</button><button className={member.is_paid ? "status-chip success" : "status-chip"} onClick={() => setPending({ scope: "individual", member, field: "is_paid", value: !member.is_paid })}>{member.is_paid ? "Оплачено" : "Не оплачено"}</button><button disabled className={member.merch_issued ? "status-chip success" : "status-chip"} title="Выдача мерча отключена для этого фестиваля">{member.merch_size ? `${member.merch_size} · выдача отключена` : "Не заказан"}</button></div>)}</div>
    </> : <div className="no-selection"><Users size={32}/><h2>Клубов пока нет</h2><p>Они появятся автоматически из заявок участников.</p></div>}</div>
    </div>
    {pending && <ConfirmDialog title={`${actionLabel}?`} description={pending.scope === "bulk" ? `Статус будет изменён у ${targetCount} участников клуба «${club?.name}» одной операцией.` : `Изменить статус участника №${pending.member.start_number}: ${pending.member.full_name}.`} confirmLabel={actionLabel} busy={saving} onCancel={() => setPending(null)} onConfirm={() => void applyAction()}/>} 
    {editingClub && <ConfirmDialog title="Редактировать клуб" description="Название и представитель обновятся у всех участников клуба." confirmLabel="Сохранить изменения" busy={saving} onCancel={() => setEditingClub(false)} onConfirm={() => void saveClub()}><div className="club-edit-form"><label>Название клуба<input value={clubDraft.name} maxLength={200} onChange={(event) => setClubDraft((value) => ({ ...value, name: event.target.value }))}/></label><label>Представитель<input value={clubDraft.representative} maxLength={200} placeholder="ФИО представителя" onChange={(event) => setClubDraft((value) => ({ ...value, representative: event.target.value }))}/></label></div></ConfirmDialog>}
    {mergeTarget && club && <ConfirmDialog title="Объединить заявки клуба?" description={`Клуб «${club.name}» будет объединён с «${mergeTarget.name}» — представитель ${mergeTarget.representative || "не указан"}. Все ${club.participant_count + mergeTarget.participant_count} участников окажутся в одной заявке.`} confirmLabel="Объединить заявки" busy={saving} onCancel={() => setMergeTarget(null)} onConfirm={() => void saveClub(true)}/>} 
    {notice && <RouteToast notification={notice} onClose={() => setNotice(null)}/>} 
  </section>;
}
