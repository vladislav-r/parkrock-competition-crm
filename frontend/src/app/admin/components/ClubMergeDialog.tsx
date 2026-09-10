"use client";

import { useState } from "react";
import { Club, mergeClubs } from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";

export function ClubMergeDialog({ token, source, clubs, onCancel, onMerged }: {
  token: string; source: Club; clubs: Club[]; onCancel: () => void;
  onMerged: (id: string, count: number) => void;
}) {
  const [choices] = useState(clubs.filter((club) => club.id !== source.id));
  const [targetId, setTargetId] = useState("");
  const [nameId, setNameId] = useState(source.id);
  const [representativeId, setRepresentativeId] = useState(source.id);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [operationId, setOperationId] = useState(() => crypto.randomUUID());
  const target = choices.find((club) => club.id === targetId);
  const pair = target ? [source, target] : [source];
  const name = pair.find((club) => club.id === nameId)?.name;
  const representative = pair.find((club) => club.id === representativeId)?.representative;
  async function submit() {
    if (!target || busy) return;
    setBusy(true); setError("");
    try {
      const result = await mergeClubs(token, source.id, {
        target_club_id: target.id, expected_version: source.version, target_expected_version: target.version,
        name_club_id: nameId, representative_club_id: representativeId,
        source_member_ids: source.members.map((member) => member.id),
        target_member_ids: target.members.map((member) => member.id),
      }, operationId);
      onMerged(result.id, result.participant_count);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Не удалось объединить клубы");
    } finally { setBusy(false); }
  }
  return <ConfirmDialog key={confirmed ? "confirmation" : "preview"} title={confirmed ? "Подтвердить объединение клубов?" : "Объединить клубы"}
    description={confirmed
      ? `«${source.name}» и «${target?.name}» станут одним клубом «${name}». Представитель: ${representative || "не указан"}. Участников: ${source.participant_count + (target?.participant_count ?? 0)}.`
      : `Выбран клуб «${source.name}». Выберите второй клуб и итоговые данные.`}
    confirmLabel={confirmed ? "Подтвердить объединение" : "Объединить"}
    confirmDisabled={!target} safeDestructive={confirmed} busy={busy}
    onCancel={() => { if (!busy) onCancel(); }}
    onConfirm={() => { if (confirmed) void submit(); else setConfirmed(true); }}>
    {confirmed ? <p className="merge-backup-note">Перед объединением будет создана резервная копия с названиями обоих клубов. Откат доступен с правом восстановления базы в разделе «Резервные копии»: он восстановит всю базу, включая остальные данные, на момент копии.</p> : <div className="club-edit-form">
      <label>Объединить с клубом<select value={targetId} onChange={(event) => { setTargetId(event.target.value); setNameId(source.id); setRepresentativeId(source.id); setOperationId(crypto.randomUUID()); }}>
        <option value="">Выберите клуб</option>{choices.map((club) => <option key={club.id} value={club.id}>{club.name} · {club.representative || "Без представителя"}</option>)}
      </select></label>
      {target && <>
        <label>Итоговое название<select value={nameId} onChange={(event) => { setNameId(event.target.value); setOperationId(crypto.randomUUID()); }}>{pair.map((club, index) => <option key={club.id} value={club.id}>{club.name} (клуб {index + 1})</option>)}</select></label>
        <label>Итоговый представитель<select value={representativeId} onChange={(event) => { setRepresentativeId(event.target.value); setOperationId(crypto.randomUUID()); }}>{pair.map((club, index) => <option key={club.id} value={club.id}>{club.representative || "Не указан"} (клуб {index + 1})</option>)}</select></label>
        <div className="merge-members">{pair.map((club) => <details key={club.id} open><summary>{club.name}: {club.participant_count} участников</summary><ul>{club.members.map((member) => <li key={member.id}>№{member.start_number} · {member.full_name}</li>)}</ul></details>)}</div>
        <strong className="merge-total">После объединения: {source.participant_count} + {target.participant_count} = {source.participant_count + target.participant_count} участников</strong>
      </>}
    </div>}
    {error && <p role="alert" className="merge-error">{error}</p>}
  </ConfirmDialog>;
}
