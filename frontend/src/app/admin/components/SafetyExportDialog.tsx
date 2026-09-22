"use client";

import { useState } from "react";
import { getSafetyExport } from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";

export function SafetyExportDialog({ token, club, onClose }: { token: string; club?: { id: string; name: string }; onClose: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function prepare(format: "pdf" | "xlsx") {
    if (busy) return;
    const preview = format === "pdf" ? window.open("about:blank", "_blank") : null;
    if (format === "pdf" && !preview) { setError("Разрешите открытие новой вкладки для печати."); return; }
    if (preview) { preview.opener = null; preview.document.title = "Подготовка журнала ТБ"; preview.document.body.textContent = "Подготавливаем журнал ТБ…"; }
    setBusy(true); setError("");
    try {
      const url = URL.createObjectURL(await getSafetyExport(token, format, club?.id));
      if (preview) preview.location.href = url;
      else {
        const link = document.createElement("a"); link.href = url;
        link.download = `ТБ — ${club?.name ?? "все клубы"}.xlsx`;
        document.body.appendChild(link); link.click(); link.remove();
      }
      window.setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (reason) { preview?.close(); setError(reason instanceof Error ? reason.message : "Не удалось сформировать журнал ТБ"); }
    finally { setBusy(false); }
  }
  return <ConfirmDialog title="Печать ТБ" description={club ? `Журнал инструктажа клуба «${club.name}».` : "Все клубы в одном документе. Каждый клуб начинается с новой страницы."}
    busy={busy} confirmLabel="Открыть для печати" onConfirm={() => void prepare("pdf")} onCancel={onClose}
    extraActions={<button type="button" disabled={busy} onClick={() => void prepare("xlsx")}>Скачать Excel</button>}>
    <p>А4, книжная ориентация. Шапка — в начале каждого клуба, дата инструктажа и подпись — в конце.</p>
    {error && <div className="error-banner" role="alert">{error}</div>}
  </ConfirmDialog>;
}
