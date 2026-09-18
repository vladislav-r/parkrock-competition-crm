"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, Clock3, Download, FileSpreadsheet, Trash2, Upload } from "lucide-react";
import { ApiError, ApplicationFile, deleteApplication, downloadApplication, getApplications, importApplication } from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";
import { RouteToast, type RouteNotification } from "./RoutesSection";
import { uploadApplication, type ImportPreview } from "@/lib/api";
import { X } from "lucide-react";

type PendingAction = {
  kind: "import" | "delete";
  item: ApplicationFile;
  skipDuplicates?: boolean;
  allowOverflow?: boolean;
  title?: string;
  description?: string;
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function formatSize(bytes: number) {
  return bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} КБ` : `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
}

export function ApplicationsSection({ token, onImported }: { token: string; onImported: () => void }) {
  const [items, setItems] = useState<ApplicationFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [notice, setNotice] = useState<RouteNotification | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [invalidRows, setInvalidRows] = useState<ImportPreview["rows"]>([]);
  const uploadLock = useRef(false);
  const fileInput = useRef<HTMLInputElement>(null);

  async function upload(files: FileList | null) {
    if (!files?.length || uploadLock.current) return;
    setUploadError(""); setInvalidRows([]); setDragging(false);
    if (files.length !== 1) { setUploadError("Загружайте по одной заявке за раз."); return; }
    const file = files[0];
    if (!/\.(xlsx|xlsm)$/i.test(file.name)) { setUploadError("Выберите файл XLSX или XLSM."); return; }
    if (file.size > 10 * 1024 * 1024) { setUploadError("Размер файла не должен превышать 10 МБ."); return; }
    uploadLock.current = true; setUploading(true);
    try {
      const saved = await uploadApplication(token, file);
      setUploadOpen(false);
      await load();
      setNotice({ type: "success", title: `Заявка «${saved.filename}» доступна в списке`, details: "Файл сохранён. Участники не добавлялись." });
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : "Не удалось загрузить заявку");
      const detail = error instanceof ApiError ? error.detail as Partial<ImportPreview> | null : null;
      if (Array.isArray(detail?.rows)) setInvalidRows(detail.rows.filter(row => Object.keys(row.errors).length > 0));
    } finally { uploadLock.current = false; setUploading(false); }
  }

  const load = useCallback(async () => {
    try { setItems(await getApplications(token)); }
    catch (error) { setNotice({ type: "error", title: error instanceof Error ? error.message : "Не удалось загрузить заявки" }); }
    finally { setLoading(false); }
  }, [token]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 5000);
    return () => window.clearInterval(timer);
  }, [load]);

  async function download(item: ApplicationFile) {
    try { await downloadApplication(token, item); }
    catch (error) { setNotice({ type: "error", title: error instanceof Error ? error.message : "Не удалось скачать заявку" }); }
  }

  async function confirmAction() {
    if (!pending) return;
    setBusy(true);
    try {
      if (pending.kind === "delete") {
        await deleteApplication(token, pending.item.id);
        setNotice({ type: "success", title: `Заявка «${pending.item.filename}» удалена` });
      } else {
        const result = await importApplication(token, pending.item.id, pending.skipDuplicates, pending.allowOverflow);
        setNotice({ type: "success", title: `Импортировано участников: ${result.imported}` });
        onImported();
      }
      setPending(null);
      await load();
    } catch (error) {
      const detail = error instanceof ApiError && typeof error.detail === "object" && error.detail ? error.detail as { code?: string; duplicate_rows?: number; sets?: Array<{ overflow_by: number }> } : null;
      if (pending.kind === "import" && detail?.code === "duplicate_participants" && !pending.skipDuplicates) {
        setPending({ ...pending, skipDuplicates: true, title: "Импортировать только новых участников?", description: `Обнаружено дубликатов: ${detail.duplicate_rows ?? 0}. Они будут пропущены.` });
      } else if (pending.kind === "import" && detail?.code === "set_capacity_overflow" && !pending.allowOverflow) {
        const overflow = detail.sets?.reduce((sum, item) => sum + item.overflow_by, 0) ?? 0;
        setPending({ ...pending, allowOverflow: true, title: "Разрешить переполнение сетов?", description: `Вместимость сетов будет превышена на ${overflow} участников.` });
      } else {
        setPending(null);
        setNotice({ type: "error", title: error instanceof Error ? error.message : "Не удалось выполнить действие" });
      }
    } finally { setBusy(false); }
  }

  return <section className="applications-section"><div className="admin-workspace-container">
    <header className="applications-head admin-section-hero"><div><h1>Заявки</h1><p>Файлы с лендинга и из CRM. Добавление участников выполняется отдельно.</p></div><div className="applications-header-actions"><button className="import-button" onClick={() => { setUploadError(""); setInvalidRows([]); setUploadOpen(true); }}><Upload size={15}/>Импорт</button><span className="applications-count"><FileSpreadsheet size={18}/><span><strong>{items.length}</strong><small>заявок</small></span></span></div></header>
    <div className="applications-relief-card"><div className="applications-relief-body">
    {loading ? <div className="applications-empty">Загружаем заявки…</div> : items.length === 0 ? <div className="applications-empty"><FileSpreadsheet size={32}/><strong>Заявок пока нет</strong><span>Нажмите «Импорт», чтобы загрузить XLSX или XLSM. Заявки с лендинга также появятся здесь.</span></div> : <div className="applications-table-wrap"><table className="applications-table"><thead><tr><th>Файл</th><th>Загружен</th><th>Участники</th><th>Статус</th><th>Действия</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><div className="application-file"><span className="application-file-icon"><FileSpreadsheet size={20}/></span><div><strong>{item.filename}</strong><small>{formatSize(item.file_size)}</small></div></div></td><td data-label="Загружен">{formatDate(item.uploaded_at)}</td><td data-label="Участники"><strong>{item.participant_count}</strong>{(item.duplicate_rows > 0 || item.overflow_sets > 0) && <small>{item.duplicate_rows > 0 ? `Дубликаты: ${item.duplicate_rows}` : ""}{item.duplicate_rows > 0 && item.overflow_sets > 0 ? " · " : ""}{item.overflow_sets > 0 ? `Переполнено сетов: ${item.overflow_sets}` : ""}</small>}</td><td data-label="Статус"><span className={`application-status ${item.status}`}>{item.status === "imported" ? <CheckCircle2 size={14}/> : <Clock3 size={14}/>}{item.status === "imported" ? "Импортирована ранее" : "Ожидает импорта"}</span>{item.imported_at && <small>Последний импорт: {formatDate(item.imported_at)}{item.import_count > 1 ? ` · всего ${item.import_count}` : ""}</small>}</td><td><div className="application-actions"><button title="Скачать файл заявки" onClick={() => void download(item)}><Download size={14}/>Скачать</button><button className="primary" onClick={() => setPending({ kind: "import", item })}><Upload size={14}/>{item.status === "imported" ? "Импорт заново" : "Импортировать"}</button><button className="danger" title="Удалить заявку" onClick={() => setPending({ kind: "delete", item })}><Trash2 size={14}/></button></div></td></tr>)}</tbody></table></div>}
    </div></div>
    {pending && <ConfirmDialog title={pending.title ?? (pending.kind === "delete" ? "Удалить заявку?" : pending.item.status === "imported" ? "Импортировать заявку заново?" : "Импортировать участников?")} description={pending.description ?? (pending.kind === "delete" ? `Файл «${pending.item.filename}» будет удалён из базы. Уже импортированные участники останутся в системе.` : pending.item.status === "imported" ? `Файл «${pending.item.filename}» будет проверен заново. Существующие участники будут показаны как дубликаты, удалённые получат новые свободные номера.` : `Участники из файла «${pending.item.filename}» будут добавлены в назначенные сеты.`)} confirmLabel={pending.kind === "delete" ? "Удалить заявку" : pending.item.status === "imported" ? "Импортировать заново" : "Импортировать"} danger={pending.kind === "delete"} busy={busy} onCancel={() => setPending(null)} onConfirm={() => void confirmAction()}/>} 
    {uploadOpen && <div className="modal-backdrop" role="presentation" onMouseDown={() => { if (!uploading) setUploadOpen(false); }}><section className="import-dialog application-upload-dialog" role="dialog" aria-modal="true" aria-labelledby="application-upload-title" onMouseDown={event => event.stopPropagation()} onKeyDown={event => { if (event.key === "Escape" && !uploading) setUploadOpen(false); }}>
      <button className="dialog-close" title="Закрыть" disabled={uploading} onClick={() => setUploadOpen(false)}><X size={18}/></button>
      <h2 id="application-upload-title">Импорт файла заявки</h2><p>Загрузите заполненный шаблон. Файл появится в списке для скачивания и последующего импорта участников.</p>
      <div className={`application-drop-zone${dragging ? " dragging" : ""}`} aria-busy={uploading} onDragOver={event => { event.preventDefault(); event.dataTransfer.dropEffect = uploading ? "none" : "copy"; if (!uploading) setDragging(true); }} onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setDragging(false); }} onDrop={event => { event.preventDefault(); void upload(event.dataTransfer.files); }}>
        <Upload size={28}/><strong>{uploading ? "Проверяем и сохраняем файл…" : "Перетащите заявку сюда"}</strong><span>XLSX или XLSM · до 10 МБ</span>
        <button className="import-button" autoFocus disabled={uploading} onClick={() => fileInput.current?.click()}>Выбрать файл</button><input ref={fileInput} type="file" hidden accept=".xlsx,.xlsm" disabled={uploading} aria-label="Файл заявки" onChange={event => { void upload(event.target.files); event.target.value = ""; }}/>
      </div>
      {uploadError && <div className="application-upload-errors" role="alert"><strong>{uploadError}</strong>{invalidRows.map(row => <div key={row.row_number}><b>Строка {row.row_number}</b>{Object.entries(row.errors).map(([field, message]) => <p key={field}>{field}: {message}</p>)}</div>)}</div>}
    </section></div>}
    {notice && <RouteToast notification={notice} onClose={() => setNotice(null)}/>} 
  </div></section>;
}
