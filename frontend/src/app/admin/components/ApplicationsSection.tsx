"use client";

import { useCallback, useEffect, useState } from "react";
import { Download, FileSpreadsheet, Trash2, Upload } from "lucide-react";
import { ApiError, ApplicationFile, deleteApplication, downloadApplication, getApplications, importApplication } from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";
import { RouteToast, type RouteNotification } from "./RoutesSection";

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
    <header className="applications-head admin-section-hero"><div><div className="eyebrow">Регистрация</div><h1>Заявки</h1><p>Файлы, отправленные с лендинга. Участники появятся в системе только после импорта.</p></div><span className="applications-count"><FileSpreadsheet size={18}/>{items.length}</span></header>
    {loading ? <div className="applications-empty">Загружаем заявки…</div> : items.length === 0 ? <div className="applications-empty"><FileSpreadsheet size={32}/><strong>Заявок пока нет</strong><span>После отправки XLSX или XLSM с лендинга файл появится здесь автоматически.</span></div> : <div className="applications-table-wrap"><table className="applications-table"><thead><tr><th>Файл</th><th>Загружен</th><th>Участники</th><th>Статус</th><th>Действия</th></tr></thead><tbody>{items.map((item) => <tr key={item.id}><td><strong>{item.filename}</strong><small>{formatSize(item.file_size)}</small></td><td>{formatDate(item.uploaded_at)}</td><td><strong>{item.participant_count}</strong>{(item.duplicate_rows > 0 || item.overflow_sets > 0) && <small>{item.duplicate_rows > 0 ? `Дубликаты: ${item.duplicate_rows}` : ""}{item.duplicate_rows > 0 && item.overflow_sets > 0 ? " · " : ""}{item.overflow_sets > 0 ? `Переполнено сетов: ${item.overflow_sets}` : ""}</small>}</td><td><span className={`application-status ${item.status}`}>{item.status === "imported" ? "Импортирована ранее" : "Ожидает импорта"}</span>{item.imported_at && <small>Последний импорт: {formatDate(item.imported_at)}{item.import_count > 1 ? ` · всего ${item.import_count}` : ""}</small>}</td><td><div className="application-actions"><button title="Скачать файл заявки" onClick={() => void download(item)}><Download size={14}/>Скачать</button><button className="primary" onClick={() => setPending({ kind: "import", item })}><Upload size={14}/>{item.status === "imported" ? "Импорт заново" : "Импортировать"}</button><button className="danger" title="Удалить заявку" onClick={() => setPending({ kind: "delete", item })}><Trash2 size={14}/></button></div></td></tr>)}</tbody></table></div>}
    {pending && <ConfirmDialog title={pending.title ?? (pending.kind === "delete" ? "Удалить заявку?" : pending.item.status === "imported" ? "Импортировать заявку заново?" : "Импортировать участников?")} description={pending.description ?? (pending.kind === "delete" ? `Файл «${pending.item.filename}» будет удалён из базы. Уже импортированные участники останутся в системе.` : pending.item.status === "imported" ? `Файл «${pending.item.filename}» будет проверен заново. Существующие участники будут показаны как дубликаты, удалённые получат новые свободные номера.` : `Участники из файла «${pending.item.filename}» будут добавлены в назначенные сеты.`)} confirmLabel={pending.kind === "delete" ? "Удалить заявку" : pending.item.status === "imported" ? "Импортировать заново" : "Импортировать"} danger={pending.kind === "delete"} busy={busy} onCancel={() => setPending(null)} onConfirm={() => void confirmAction()}/>} 
    {notice && <RouteToast notification={notice} onClose={() => setNotice(null)}/>} 
  </div></section>;
}
