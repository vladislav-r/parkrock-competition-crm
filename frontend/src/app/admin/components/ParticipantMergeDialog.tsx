"use client";

import { useState } from "react";
import { CircleAlert } from "lucide-react";
import { EventInfo, Participant, ParticipantEdit, ParticipantMergeChoices, mergeParticipants } from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";

export function ParticipantMergeDialog({ token, source, target, draft, event, onCancel, onMerged }: {
  token: string; source: Participant; target: Participant; draft: ParticipantEdit; event: EventInfo;
  onCancel: () => void; onMerged: (participant: Participant) => void;
}) {
  const [choices, setChoices] = useState<ParticipantMergeChoices>({
    primary_participant_id: target.id, club_participant_id: target.id, representative_participant_id: target.id,
    rank_participant_id: target.id, arrival_participant_id: target.id, payment_participant_id: target.id,
  });
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [operationId, setOperationId] = useState(() => crypto.randomUUID());
  const pair = [source, target];
  const chosen = (key: keyof ParticipantMergeChoices) => pair.find((p) => p.id === choices[key])!;
  const setName = (p: Participant) => event.sets.find((s) => s.id === p.set_id)?.name ?? "Сет не найден";
  const fullName = (p: Participant | ParticipantEdit) => [p.surname, p.name, p.patronymic].filter(Boolean).join(" ");
  const fields: { key: keyof ParticipantMergeChoices; label: string; value: (p: Participant) => string }[] = [
    {key: "primary_participant_id", label: "Основная запись: номер и сет", value: (p) => `№${p.start_number} · ${setName(p)}`},
    {key: "club_participant_id", label: "Клуб", value: (p) => p.club},
    {key: "representative_participant_id", label: "Представитель", value: (p) => p.representative || "Не указан"},
    {key: "rank_participant_id", label: "Разряд", value: (p) => p.sport_rank},
    {key: "arrival_participant_id", label: "Прибытие", value: (p) => p.checked_in_at ? "Прибыл" : "Не прибыл"},
    {key: "payment_participant_id", label: "Оплата", value: (p) => p.is_paid ? "Оплачено" : "Не оплачено"},
  ];
  const primary = chosen("primary_participant_id");
  const removed = pair.find((p) => p.id !== primary.id)!;
  async function submit() {
    if (busy) return;
    setBusy(true); setError("");
    try { onMerged((await mergeParticipants(token, source, target, draft, choices, operationId)).participant); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось объединить участников"); }
    finally { setBusy(false); }
  }
  return <ConfirmDialog key={confirmed ? "confirm-merge" : "preview-merge"}
    title={confirmed ? "Подтвердить объединение участников?" : "Объединить две записи участника"}
    description={confirmed ? `Останется участник №${primary.start_number}. Запись №${removed.start_number} будет удалена.` : "Убедитесь, что это один человек, и выберите итоговые данные. После объединения останется одна запись."}
    confirmLabel={confirmed ? "Подтвердить объединение" : "Объединить"} safeDestructive={confirmed} danger
    busy={busy} onCancel={() => { if (!busy) onCancel(); }} onConfirm={() => confirmed ? void submit() : setConfirmed(true)}>
    {!confirmed && <div className="participant-merge-pair">{pair.map((p) => <article key={p.id}>
      <strong>№{p.start_number} · {fullName(p)}</strong><span>{p.birth_year} г. р. · {setName(p)}</span>
      <span>{p.club} · {p.sport_rank}</span><span>Представитель: {p.representative || "Не указан"}</span>
      <span>{p.checked_in_at ? "Прибыл" : "Не прибыл"} · {p.is_paid ? "Оплачено" : "Не оплачено"}</span>
    </article>)}</div>}
    <div className="participant-edit-notice"><CircleAlert size={20} aria-hidden="true"/><div>
      <strong>{fullName(draft)}, {draft.birth_year} г. р.</strong>
      <span>ФИО, год рождения и пол ({draft.sex === "male" ? "мужской" : "женский"}) — из исправленных данных. Группа определится автоматически.</span>
    </div></div>
    <div className="club-edit-form participant-merge-fields">{fields.map(({key, label, value}) => confirmed
      ? <div key={key} className="participant-merge-result"><strong>{label}</strong><span>{value(chosen(key))}</span></div>
      : <label key={key}>{label}<select disabled={busy} value={choices[key]} onChange={(e) => {
        setChoices((current) => ({...current, [key]: e.target.value})); setOperationId(crypto.randomUUID()); setError("");
      }}>{pair.map((p) => <option key={p.id} value={p.id}>{value(p)} — запись №{p.start_number}</option>)}</select></label>)}</div>
    <p className="merge-backup-note">Тип заявки и данные мерча сохраняются из основной записи. Перед объединением будет создана проверенная резервная копия. Откат через «Резервные копии» восстановит всю базу на момент копии.</p>
    {confirmed && <button className="secondary-button" disabled={busy} onClick={() => setConfirmed(false)}>Изменить выбор данных</button>}
    {error && <div role="alert" className="participant-edit-alert"><CircleAlert size={20} aria-hidden="true"/><div><strong>Объединение не выполнено</strong><span>{error}</span></div></div>}
  </ConfirmDialog>;
}
