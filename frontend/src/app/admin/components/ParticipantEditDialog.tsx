"use client";

import { useEffect, useRef, useState } from "react";
import { CircleAlert } from "lucide-react";
import { ApiError, Club, EventInfo, Participant, ParticipantEdit, editParticipant, getClubs } from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";
import { ParticipantMergeDialog } from "./ParticipantMergeDialog";

const labels: Record<keyof ParticipantEdit, string> = {
  surname: "Фамилия", name: "Имя", patronymic: "Отчество", birth_year: "Год рождения", sex: "Пол",
  sport_rank: "Разряд", club: "Клуб", representative: "Представитель",
};
export function ParticipantEditDialog({ token, participant, event, canMerge, onClose, onSaved }: {
  token: string; participant: Participant; event: EventInfo; canMerge: boolean; onClose: () => void; onSaved: (participant: Participant) => void;
}) {
  const [draft, setDraft] = useState<ParticipantEdit>({surname: participant.surname, name:participant.name, patronymic:participant.patronymic ?? "",
    birth_year:participant.birth_year, sex:participant.sex, sport_rank:participant.sport_rank, club:participant.club, representative:participant.representative});
  const [clubs, setClubs] = useState<Club[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [duplicates, setDuplicates] = useState<Participant[]>([]);
  const [merging, setMerging] = useState(false);
  const errorRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (error && !merging) {
      errorRef.current?.focus({preventScroll: true});
      errorRef.current?.scrollIntoView({block: "center", behavior: "instant"});
    }
  }, [error, merging]);
  const [operationId, setOperationId] = useState(() => crypto.randomUUID());
  useEffect(() => { void getClubs(token).then(setClubs).catch(() => {}); }, [token]);
  const changes = (Object.keys(labels) as Array<keyof ParticipantEdit>).filter((key) => String(draft[key] ?? "").trim() !== String(participant[key] ?? "").trim());
  const year = Number(event.starts_on.slice(0,4));
  const valid = draft.name.trim() && draft.surname.trim() && draft.club.trim() && draft.sport_rank.trim() && Number.isInteger(draft.birth_year) && draft.birth_year >= year - 99 && draft.birth_year <= year;
  function change(key: keyof ParticipantEdit, value: string | number) {
    setError(""); setDuplicates([]);
    setDraft((current) => ({ ...current, [key]:value })); setOperationId(crypto.randomUUID());
  }
  const display = (key: keyof ParticipantEdit, value: unknown) => key === "sex" ? value === "male" ? "Мужской" : "Женский" : String(value || "Не указано");
  async function save() {
    setBusy(true); setError("");
    try { onSaved(await editParticipant(token, participant, draft, operationId)); }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось сохранить данные");
      if (reason instanceof ApiError && reason.detail && typeof reason.detail === "object" && "code" in reason.detail && reason.detail.code === "duplicate_participant" && "participants" in reason.detail) {
        setDuplicates(reason.detail.participants as Participant[]); setConfirming(false);
      }
    }
    finally { setBusy(false); }
  }
  if (merging && duplicates.length === 1) return <ParticipantMergeDialog token={token} source={participant} target={duplicates[0]} draft={draft} event={event} onCancel={() => setMerging(false)} onMerged={onSaved}/>;
  return <ConfirmDialog key={confirming ? "confirm" : "edit"} title={confirming ? `Сохранить изменения участника №${participant.start_number}?` : `Редактировать участника №${participant.start_number}`}
    description={confirming ? "Изменения коснутся только этого участника. Стартовый номер и назначенный сет сохранятся." : "Редактирование доступно на этапе «Подготовка». Группа определяется автоматически по полу и году рождения."}
    confirmLabel={confirming ? "Подтвердить изменения" : "Продолжить"} confirmDisabled={!valid || !changes.length || duplicates.length > 0} busy={busy} danger={Boolean(error)}
    extraActions={duplicates.length === 1 && canMerge && <button className="participant-merge-button" disabled={busy} onClick={() => setMerging(true)}>Объединить</button>}
    onCancel={() => { if (!busy) onClose(); }} onConfirm={() => confirming ? void save() : setConfirming(true)}>
    {confirming ? <div className="participant-edit-summary">{changes.map((key) => <div key={key}><strong>{labels[key]}</strong><span>{display(key, participant[key])} → {display(key,draft[key])}</span></div>)}
      {(changes.includes("birth_year") || changes.includes("sex")) && <div className="participant-edit-notice"><CircleAlert size={20} aria-hidden="true"/><span>Возрастная группа будет определена заново по исправленным данным.</span></div>}
      <button className="secondary-button" disabled={busy} onClick={() => setConfirming(false)}>Вернуться к редактированию</button>
    </div> : <div className="participant-form-grid participant-edit-form">
      {(["surname", "name", "patronymic"] as const).map((key) => <label key={key}>{labels[key]}<input disabled={busy} aria-invalid={duplicates.length > 0 || (key !== "patronymic" && !draft[key].trim())} aria-describedby={duplicates.length ? "participant-edit-error" : undefined} value={draft[key] ?? ""} maxLength={100} onChange={(e) => change(key,e.target.value)}/></label>)}
      <label>Год рождения<input disabled={busy} aria-invalid={duplicates.length > 0 || !Number.isInteger(draft.birth_year) || draft.birth_year < year-99 || draft.birth_year > year} aria-describedby={duplicates.length ? "participant-edit-error" : undefined} type="number" min={year-99} max={year} value={draft.birth_year || ""} onChange={(e) => change("birth_year",Number(e.target.value))}/></label>
      <label>Пол<select value={draft.sex} onChange={(e) => change("sex",e.target.value)}><option value="male">Мужской</option><option value="female">Женский</option></select></label>
      <label>Разряд<input value={draft.sport_rank} maxLength={50} onChange={(e) => change("sport_rank",e.target.value)}/></label>
      <label>Клуб<input value={draft.club} maxLength={200} list="edit-participant-clubs" onChange={(e) => change("club",e.target.value)}/><datalist id="edit-participant-clubs">{Array.from(new Set(clubs.map((club) => club.name))).map((name) => <option key={name} value={name}/>)}</datalist></label>
      <label>Представитель<input value={draft.representative} maxLength={200} list="edit-participant-representatives" onChange={(e) => change("representative",e.target.value)}/><datalist id="edit-participant-representatives">{Array.from(new Set(clubs.filter((club) => club.name === draft.club).map((club) => club.representative))).map((name) => <option key={name} value={name}/>)}</datalist></label>
    </div>}
    {!valid && <div role="alert" className="participant-edit-alert"><CircleAlert size={20} aria-hidden="true"/><div><strong>Проверьте обязательные поля</strong><span>Укажите фамилию, имя, клуб и разряд. Год рождения — целое число от {year-99} до {year}.</span></div></div>}
    {error && <div ref={errorRef} tabIndex={-1} id="participant-edit-error" role="alert" className="participant-edit-alert"><CircleAlert size={20} aria-hidden="true"/><div><strong>{duplicates.length ? "Найдена другая запись участника" : "Изменения не сохранены"}</strong><span>{error}</span>
      {duplicates.map((p) => <span key={p.id}>№{p.start_number} · {[p.surname,p.name,p.patronymic].filter(Boolean).join(" ")} · {p.birth_year} г. р. · {p.club}</span>)}
      {duplicates.length === 1 && <span>{canMerge ? "Если это один человек, нажмите «Объединить» и выберите итоговые данные. Если это разные люди — проверьте ФИО и год рождения." : "Для объединения обратитесь к сотруднику с правом «Объединение участников на подготовке»."}</span>}
    </div></div>}
  </ConfirmDialog>;
}
