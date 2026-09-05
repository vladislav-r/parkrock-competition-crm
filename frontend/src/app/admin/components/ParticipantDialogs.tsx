"use client";

import { useEffect, useMemo, useState } from "react";
import { CircleAlert, FileSpreadsheet, Upload, UserPlus, X } from "lucide-react";
import { ApplicationType, Club, createParticipant, EventInfo, getClubs, importParticipants, ImportPreview, ParticipantCreatePayload, previewParticipantsImport } from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";
import type { RouteNotification } from "./RoutesSection";

const IMPORT_COLUMNS = ["Фамилия", "Имя", "Отчество", "Год рождения", "Пол", "Разряд", "Сет"];
const OPTIONAL_IMPORT_COLUMNS = new Set(["Отчество"]);

export function ParticipantImportDialog({ token, onClose, onImported, onNotice }: {
  token: string;
  onClose: () => void;
  onImported: () => Promise<void>;
  onNotice: (notice: RouteNotification) => void;
}) {
  const [applicationType, setApplicationType] = useState<ApplicationType>("collective");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [allowOverflow, setAllowOverflow] = useState(false);
  const [busy, setBusy] = useState(false);

  async function inspect(selectedFile: File) {
    setBusy(true); setFile(selectedFile); setPreview(null); setAllowOverflow(false);
    try { setPreview(await previewParticipantsImport(token, selectedFile, applicationType)); }
    catch (error) { onNotice({ type: "error", title: error instanceof Error ? error.message : "Не удалось проверить файл" }); }
    finally { setBusy(false); }
  }

  async function applyImport() {
    if (!file || !preview) return;
    setBusy(true);
    try {
      const result = await importParticipants(token, file, applicationType, preview.duplicate_rows > 0, allowOverflow);
      await onImported(); onClose();
      onNotice({ type: "success", title: `Добавлено участников: ${result.imported}`, details: result.skipped_duplicates ? `Пропущено дубликатов: ${result.skipped_duplicates}` : `Стартовые номера: ${result.first_start_number}–${result.last_start_number}` });
    } catch (error) { onNotice({ type: "error", title: error instanceof Error ? error.message : "Импорт не выполнен" }); }
    finally { setBusy(false); }
  }

  const overflowConfirmed = !preview?.overflow.length || allowOverflow;
  return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><section className="import-dialog stage3-import-dialog" role="dialog" aria-modal="true" aria-labelledby="import-title" onMouseDown={(event) => event.stopPropagation()}>
    <button className="dialog-close" onClick={onClose} title="Закрыть"><X size={18}/></button>
    <div className="dialog-icon"><FileSpreadsheet size={22}/></div><div className="eyebrow">CSV или XLSX</div><h2 id="import-title">Импорт участников</h2>
    <div className="application-type-switch"><button className={applicationType === "collective" ? "active" : ""} onClick={() => { setApplicationType("collective"); setPreview(null); setFile(null); }}>Коллективная заявка</button><button className={applicationType === "individual" ? "active" : ""} onClick={() => { setApplicationType("individual"); setPreview(null); setFile(null); }}>Индивидуальные заявки</button></div>
    {!preview && <><p>Загрузите шаблон коллективной заявки. Название команды, ФИО представителя и телефон обязательны. Участники появятся в системе только после вашего подтверждения.</p><div className="import-columns">{IMPORT_COLUMNS.map((column) => <span key={column} className={OPTIONAL_IMPORT_COLUMNS.has(column) ? "optional-column" : ""}>{column}{OPTIONAL_IMPORT_COLUMNS.has(column) && <small>необязательно</small>}</span>)}</div><label className={busy ? "file-upload-button disabled" : "file-upload-button"}><Upload size={17}/>{busy ? "Проверяем файл..." : "Выбрать и проверить файл"}<input type="file" accept=".xlsx,.xlsm" disabled={busy} onChange={(event) => { const selected = event.target.files?.[0]; if (selected) void inspect(selected); }}/></label></>}
    {preview && <div className="import-preview"><div className="preview-summary"><span><strong>{preview.total_rows}</strong> строк</span><span className="preview-valid"><strong>{preview.valid_rows}</strong> готовы</span><span className={preview.duplicate_rows ? "preview-warning" : ""}><strong>{preview.duplicate_rows}</strong> дубликатов</span><span className={preview.error_rows ? "preview-error" : ""}><strong>{preview.error_rows}</strong> с ошибками</span></div>
      {preview.error_rows > 0 && <div className="import-blocker"><CircleAlert size={18}/><span>Исправьте выделенные ячейки в исходном файле и проверьте его повторно.</span></div>}
      <div className="preview-table-wrap"><table className="preview-table"><thead><tr><th>Строка</th>{IMPORT_COLUMNS.map((column) => <th key={column}>{column}</th>)}</tr></thead><tbody>{preview.rows.map((row) => <tr key={row.row_number} className={row.duplicate ? "duplicate-row" : ""}><td>{row.row_number}{row.duplicate && <small>Дубликат</small>}</td>{IMPORT_COLUMNS.map((column) => {
        const value = column === "Год рождения" ? row.values["Год рождения"] || row.values["Дата рождения"] : row.values[column];
        const error = column === "Год рождения" ? row.errors["Год рождения"] || row.errors["Дата рождения"] : row.errors[column];
        return <td key={column} className={error ? "invalid-cell" : ""}>{value || "—"}{error && <small>{error}</small>}</td>;
      })}</tr>)}</tbody></table></div>
      {preview.overflow.length > 0 && <label className="overflow-approval"><input type="checkbox" checked={allowOverflow} onChange={(event) => setAllowOverflow(event.target.checked)}/><span><strong>Подтвердить превышение вместимости</strong><small>{preview.overflow.map((item) => `${item.set_name}: ${item.projected}/${item.capacity}`).join(" · ")}</small></span></label>}
      <div className="dialog-actions"><button className="secondary-button" disabled={busy} onClick={() => { setPreview(null); setFile(null); }}>Выбрать другой файл</button><button className="primary-button" disabled={busy || !preview.can_import || !overflowConfirmed} onClick={() => void applyImport()}>{busy ? "Загружаем..." : preview.duplicate_rows ? `Загрузить ${preview.valid_rows} корректных` : `Загрузить ${preview.valid_rows}`}</button></div>
    </div>}
  </section></div>;
}

export function ParticipantCreateDialog({ token, event, onClose, onCreated, onNotice }: {
  token: string;
  event: EventInfo;
  onClose: () => void;
  onCreated: () => Promise<void>;
  onNotice: (notice: RouteNotification) => void;
}) {
  const [pending, setPending] = useState<ParticipantCreatePayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [clubs, setClubs] = useState<Club[]>([]);
  const [clubName, setClubName] = useState("");
  const [representative, setRepresentative] = useState("");
  useEffect(() => {
    void getClubs(token).then((items) => {
      setClubs(items);
      if (items.length) {
        setClubName(items[0].name);
        setRepresentative(items[0].representative);
      }
    }).catch(() => undefined);
  }, [token]);
  const clubNames = useMemo(() => Array.from(new Map(clubs.map((item) => [item.name.trim().toLocaleLowerCase("ru"), item.name])).values()), [clubs]);
  const representatives = useMemo(() => Array.from(new Set(clubs.filter((item) => item.name.trim().toLocaleLowerCase("ru") === clubName.trim().toLocaleLowerCase("ru")).map((item) => item.representative))), [clubs, clubName]);
  const eventYear = Number(event.starts_on.slice(0, 4));
  function prepare(formData: FormData) {
    const setId = String(formData.get("set_id"));
    const selectedSet = event.sets.find((item) => item.id === setId);
    setPending({
      set_id: setId, allow_overflow: Boolean(selectedSet && selectedSet.participant_count >= selectedSet.capacity), surname: String(formData.get("surname")).trim(), name: String(formData.get("name")).trim(), patronymic: String(formData.get("patronymic")).trim(),
      birth_date: String(formData.get("birth_date")), sex: String(formData.get("sex")) as "male" | "female", sport_rank: String(formData.get("sport_rank")).trim(), club: String(formData.get("club")).trim(),
      representative: String(formData.get("representative")).trim(), merch_size: null,
    });
  }
  async function create() {
    if (!pending) return;
    setBusy(true);
    try { const participant = await createParticipant(token, pending); await onCreated(); onClose(); onNotice({ type: "success", title: `Участник №${participant.start_number} добавлен` }); }
    catch (error) { setPending(null); onNotice({ type: "error", title: error instanceof Error ? error.message : "Не удалось добавить участника" }); }
    finally { setBusy(false); }
  }
  return <><div className="modal-backdrop" role="presentation" onMouseDown={onClose}><form action={prepare} className="user-editor participant-editor" onMouseDown={(event) => event.stopPropagation()}><button type="button" className="dialog-close" onClick={onClose}><X size={18}/></button><div className="dialog-icon"><UserPlus size={22}/></div><div className="eyebrow">Индивидуальная заявка</div><h2>Новый участник</h2>
    <div className="participant-form-grid"><label>Фамилия<input name="surname" required/></label><label>Имя<input name="name" required/></label><label>Отчество<input name="patronymic"/></label><label>Дата рождения<input name="birth_date" type="date" min={`${eventYear - 99}-01-01`} max={`${eventYear}-12-31`} required/></label><label>Пол<select name="sex" required><option value="male">Мужской</option><option value="female">Женский</option></select></label><label>Разряд<input name="sport_rank" defaultValue="Без разряда" required/></label>{clubNames.length ? <><label>Клуб<select name="club" value={clubName} required onChange={(event) => { const name = event.target.value; const first = clubs.find((item) => item.name === name); setClubName(name); setRepresentative(first?.representative ?? ""); }}>{clubNames.map((name) => <option key={name} value={name}>{name}</option>)}</select></label><label>Представитель<select name="representative" value={representative} onChange={(event) => setRepresentative(event.target.value)}>{representatives.map((name) => <option key={name || "empty"} value={name}>{name || "Не указан"}</option>)}</select></label></> : <><label>Клуб<input name="club" required/></label><label>Представитель<input name="representative"/></label></>}<label>Сет<select name="set_id" required>{event.sets.filter((item) => item.status !== "confirmed").map((item) => <option key={item.id} value={item.id}>{item.name} · {item.participant_count}/{item.capacity}{item.participant_count >= item.capacity ? " · переполнен" : ""}</option>)}</select></label></div>
    <button className="primary-button">Проверить и продолжить</button></form></div>
    {pending && <ConfirmDialog title={pending.allow_overflow ? "Добавить сверх вместимости?" : "Добавить участника?"} description={pending.allow_overflow ? `${pending.surname} ${pending.name} будет добавлен в уже заполненный сет. Количество участников превысит установленную вместимость.` : `${pending.surname} ${pending.name} будет добавлен как индивидуальная заявка. Система проверит дубликаты и вместимость сета.`} confirmLabel={pending.allow_overflow ? "Добавить сверх лимита" : "Добавить участника"} danger={pending.allow_overflow} busy={busy} onCancel={() => setPending(null)} onConfirm={() => void create()}/>}</>;
}
