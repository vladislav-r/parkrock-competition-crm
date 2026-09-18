"use client";

import { useEffect, useState } from "react";
import { getUserPresence, type UserPresence } from "@/lib/api";
import { UserConnection } from "./UserConnection";

// Mount only while the profile menu is open and users.presence is granted.
export function OnlineStaff({ token, currentUserId }: { token: string; currentUserId: string }) {
  const [staff, setStaff] = useState<[string, UserPresence][] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let stopped = false;
    let timer: number;
    let controller: AbortController;
    setStaff(null);
    setFailed(false);
    async function refresh() {
      controller = new AbortController();
      const timeout = window.setTimeout(() => controller.abort(), 8000);
      try {
        const data = await getUserPresence(token, controller.signal);
        if (!stopped) {
          setStaff(Object.entries(data).filter(([id, person]) => id !== currentUserId && person.status !== "offline")
            .sort((a, b) => a[1].full_name.localeCompare(b[1].full_name, "ru")));
          setFailed(false);
        }
      } catch {
        if (!stopped) setFailed(true);
      } finally {
        window.clearTimeout(timeout);
        if (!stopped) timer = window.setTimeout(refresh, 5000);
      }
    }
    void refresh();
    return () => { stopped = true; controller?.abort(); window.clearTimeout(timer); };
  }, [token, currentUserId]);

  return <section className="online-staff" aria-label="Сотрудники онлайн">
    <strong>Сотрудники онлайн</strong>
    {failed ? <p role="status">Не удалось обновить соединения</p>
      : staff === null ? <p role="status">Проверяем соединения…</p>
        : staff.length === 0 ? <p>Других сотрудников онлайн нет</p>
          : <ul>{staff.map(([id, person]) => <li key={id}>
            <span className="online-staff-name">{person.full_name}</span>
            <UserConnection presence={person} fresh/>
          </li>)}</ul>}
  </section>;
}
