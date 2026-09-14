"use client";

import { useEffect, useState } from "react";
import { ADMIN_READ_STATUS_EVENT, type AdminReadStatus } from "@/lib/api";

export function SyncStatus({ lastSyncedAt, duration }: { lastSyncedAt: number | null; duration: number | null }) {
  const [failures, setFailures] = useState<Record<string, AdminReadStatus>>({});
  const [offline, setOffline] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [mountedAt] = useState(() => Date.now());
  useEffect(() => {
    const receive = (event: Event) => {
      const detail = (event as CustomEvent<AdminReadStatus>).detail;
      setFailures((current) => {
        if (!detail.error && !current[detail.path]) return current;
        const next = { ...current };
        if (detail.error) next[detail.path] = detail;
        else delete next[detail.path];
        return next;
      });
    };
    const connection = () => setOffline(!navigator.onLine);
    connection();
    window.addEventListener(ADMIN_READ_STATUS_EVENT, receive);
    window.addEventListener("online", connection);
    window.addEventListener("offline", connection);
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => {
      window.removeEventListener(ADMIN_READ_STATUS_EVENT, receive);
      window.removeEventListener("online", connection);
      window.removeEventListener("offline", connection);
      window.clearInterval(timer);
    };
  }, []);
  const errors = Object.values(failures);
  const age = Math.max(0, Math.floor((now - (lastSyncedAt ?? mountedAt)) / 1000));
  const stale = age >= 10;
  const warning = offline || errors.length > 0 || stale;
  const label = offline ? "Нет подключения" : errors.length ? "Ошибка обновления" : stale ? "Обновление задерживается" : lastSyncedAt ? "Данные обновлены" : "Подключаемся…";
  const updated = lastSyncedAt ? new Date(lastSyncedAt).toLocaleTimeString("ru-RU") : "ещё не получены";
  return <>
    <details className={`crm-sync ${warning ? "has-error" : lastSyncedAt ? "is-current" : "is-pending"}`}>
      <summary><i aria-hidden="true"/><span>{label}<small>{lastSyncedAt ? `${age} с назад · ${duration} мс` : "Ожидаем первый ответ"}</small></span></summary>
      <div className="crm-sync-details">
        <strong>Обновление CRM</strong>
        <p>Событие и участники: каждые 3 секунды, а также при возвращении в окно и восстановлении сети.</p>
        <p>Последнее успешное обновление: {updated}. {duration !== null && `Загрузка: ${duration} мс.`}</p>
        <p>Это время получения ответа сервера. Другие разделы загружают свои данные отдельно; ошибки их загрузки также показываются здесь.</p>
      </div>
    </details>
    {warning && <div className="crm-sync-alert" role="alert">
      <div><strong>{label}. Данные могут быть устаревшими.</strong>
        {offline && <p>Браузер сообщает об отсутствии сети.</p>}
        {errors.map((item) => <div key={item.path}><p>{item.error}</p><details><summary>Подробности запроса</summary><code>{item.path}</code><span>Последняя ошибка: {new Date(item.at).toLocaleTimeString("ru-RU")}</span></details></div>)}
        {stale && !offline && errors.length === 0 && <p>Нет успешного обновления уже {age} с. Ожидаем ответ сервера.</p>}
        <small>Последнее успешное обновление события и участников: {updated}.</small>
      </div>
      <button type="button" onClick={() => window.location.reload()}>Перезагрузить страницу</button>
    </div>}
  </>;
}
