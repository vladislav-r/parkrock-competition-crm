"use client";

import { useCallback, useEffect, useState } from "react";
import { getJudgeConflicts, JudgeAttemptValue, JudgeConflict, resolveJudgeConflict } from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";

const describe = (value: JudgeAttemptValue | null | undefined) => value
  ? `Зона: ${value.zone_attempt ?? "—"} · Топ: ${value.top_attempt ?? "—"}`
  : "Результат отсутствует";

export function JudgeConflictsPanel({ token, onUpdated }: { token: string; onUpdated: () => Promise<void> }) {
  const [items, setItems] = useState<JudgeConflict[]>([]);
  const [pending, setPending] = useState<{ item: JudgeConflict; choice: "server" | "judge"; operationId: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try { setItems(await getJudgeConflicts(token)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Не удалось загрузить конфликты"); }
  }, [token]);
  useEffect(() => {
    void load();
    const interval = window.setInterval(() => void load(), 3000);
    return () => window.clearInterval(interval);
  }, [load]);
  async function resolve() {
    if (!pending) return;
    setBusy(true); setError("");
    try {
      await resolveJudgeConflict(token, pending.item, pending.choice, pending.operationId);
      setPending(null); await load(); await onUpdated();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось разрешить конфликт");
      // A fresh comparison is required after another staff member changed the result.
      if (reason instanceof Error && "status" in reason && reason.status === 409) setPending(null);
      await load();
    } finally { setBusy(false); }
  }
  if (!items.length && !error) return null;
  return <section className="judge-conflicts-panel">
    <h2>Конфликты результатов судей · {items.length}</h2>
    <p>Результаты с ноутбуков сохранены. До вашего решения действует серверное значение.</p>
    {error && <p role="alert" className="judge-error">{error}</p>}
    {items.map((item) => <article key={item.id}>
      <h3>№{item.start_number} · {item.full_name} · {item.route_name}</h3>
      <div className="judge-conflict-values">
        <div><strong>Сейчас на сервере</strong><p>{describe(item.current)}</p></div>
        <div><strong>От судьи · {item.judge_name}</strong><p>{describe(item.submitted)}</p></div>
      </div>
      <small>На сервере при доставке: {describe(item.server_at_submission)}</small>
      <div className="dialog-actions">
        <button className="secondary-button" onClick={() => setPending({ item, choice: "server", operationId: crypto.randomUUID() })}>Оставить серверный</button>
        <button className="confirm-results-button" disabled={!item.can_apply_judge} onClick={() => setPending({ item, choice: "judge", operationId: crypto.randomUUID() })}>Принять результат судьи</button>
      </div>
    </article>)}
    {pending && <ConfirmDialog title={`Выбрать результат №${pending.item.start_number}?`}
      description={`Будет выбран ${pending.choice === "judge" ? "результат судьи" : "серверный результат"}: ${describe(pending.choice === "judge" ? pending.item.submitted : pending.item.current)}. Оба значения и ваше решение сохранятся в истории.`}
      confirmLabel="Подтвердить выбор" busy={busy} onCancel={() => { if (!busy) setPending(null); }} onConfirm={() => void resolve()} />}
  </section>;
}
