import type { UserPresence } from "@/lib/api";

export function UserConnection({ presence, fresh }: { presence?: UserPresence; fresh: boolean }) {
  if (!presence || !fresh) return <span className="user-connection unknown">Нет актуальных данных</span>;
  const age = presence.age_seconds;
  const ago = age === null ? "ещё не подключался" : age < 60 ? "был менее минуты назад"
    : age < 3600 ? `был ${Math.floor(age / 60)} мин. назад`
      : age < 86400 ? `был ${Math.floor(age / 3600)} ч. назад` : `был ${Math.floor(age / 86400)} дн. назад`;
  const label = presence.status === "online" ? "Онлайн" : presence.status === "unstable" ? "Нестабильно" : "Оффлайн";
  return <span className={`user-connection ${presence.status}`} title={presence.last_seen ? `Последняя связь: ${new Date(presence.last_seen).toLocaleString("ru-RU")}` : "Сигналов от приложения пока нет"}>
    <span className="connection-dot" aria-hidden="true"/>
    <span>{label} · {presence.status === "offline" ? ago : `${presence.latency_ms?.toLocaleString("ru-RU")} мс`}</span>
  </span>;
}
