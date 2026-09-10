"use client";

import { useCallback, useEffect, useState } from "react";
import { Download, FileSpreadsheet } from "lucide-react";
import { ApiError, downloadExport, ExportItem, getExportCatalog } from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";

export function ExportsSection({ token }: { token: string }) {
  const [items, setItems] = useState<ExportItem[]>([]);
  const [view, setView] = useState<"results" | "other">("results");
  const [pending, setPending] = useState<ExportItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const load = useCallback(async () => {
    try { setItems((await getExportCatalog(token)).items); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось загрузить выгрузки"); }
  }, [token]);
  useEffect(() => { void load(); const timer = window.setInterval(() => void load(), 5000); return () => window.clearInterval(timer); }, [load]);
  async function download() {
    if (!pending) return;
    setBusy(true); setError(""); setNotice("");
    try { await downloadExport(token, pending, pending.warnings.length > 0); setNotice(`Файл «${pending.title}» подготовлен`); setPending(null); }
    catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось скачать XLSX");
      if (reason instanceof ApiError && reason.status === 409) { setPending(null); await load(); }
    } finally { setBusy(false); }
  }
  const blocks = view === "results" ? [["qualification", "Квалификация"], ["final", "Финал"], ["absolute", "Абсолют"]] : [["other", "Другие выгрузки"]];
  return <section className="exports-workspace">
    <header className="admin-section-hero"><div><div className="eyebrow">Документы соревнования</div><h1>Выгрузки</h1><p>Протоколы и списки участников в XLSX.</p></div><FileSpreadsheet size={32}/></header>
    <nav className="settings-tabs exports-tabs" aria-label="Подразделы выгрузок"><button className={view === "results" ? "active" : ""} onClick={() => setView("results")}>Результаты</button><button className={view === "other" ? "active" : ""} onClick={() => setView("other")}>Другие выгрузки</button></nav>
    {error && <div className="error-banner" role="alert">{error}</div>}
    {notice && <p role="status">{notice}</p>}
    {blocks.map(([block, label]) => <section className="exports-block" key={block}><h2>{label}</h2><div className="exports-card-grid">
      {items.filter((item) => item.block === block).map((item) => <article className={`export-card ${!item.available ? "unavailable" : ""}`} key={item.key}>
        <h3>{item.title}</h3><p>{item.available ? `${item.row_count} записей с данными` : item.reason}</p>
        {item.warnings.map((warning) => <p className="export-warning" key={warning}>{warning}</p>)}
        <button className="secondary-button" disabled={!item.available || busy} title={item.reason || "Скачать XLSX"} onClick={() => { setError(""); setPending(item); }}><Download size={16}/>Скачать XLSX</button>
      </article>)}
    </div>{!items.length && <p>Загрузка доступных выгрузок…</p>}</section>)}
    {pending && <ConfirmDialog title={`Выгрузить «${pending.title}»?`} description={pending.warnings.length ? `Данных недостаточно для полного протокола. ${pending.warnings.join(" ")} Продолжить?` : `Будет сформирован файл XLSX: ${pending.row_count} записей с данными.`}
      confirmLabel="Скачать XLSX" busy={busy} onCancel={() => { if (!busy) setPending(null); }} onConfirm={() => void download()}/>}
  </section>;
}
