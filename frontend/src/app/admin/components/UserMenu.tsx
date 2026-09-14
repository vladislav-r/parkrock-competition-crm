"use client";

import { useEffect, useRef } from "react";
import { BookOpen, ChevronDown, LogOut, Settings, UserRound } from "lucide-react";
import type { CurrentUser, UserRole } from "@/lib/api";

export function UserMenu({ user, onGuide, onSettings, onLogout }: { user: CurrentUser; onGuide: () => void; onSettings?: () => void; onLogout: () => void }) {
  const ref = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const closeOutside = (event: PointerEvent) => { if (!ref.current?.contains(event.target as Node)) ref.current?.removeAttribute("open"); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape" && ref.current?.open) { ref.current.open = false; ref.current.querySelector("summary")?.focus(); } };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", closeOutside); document.removeEventListener("keydown", escape); };
  }, []);
  function run(action: () => void) { if (ref.current) ref.current.open = false; action(); }
  const roles: Record<UserRole, string> = { administrator: "Администратор", chief_judge: "Главный судья", secretary: "Секретарь", reception: "Ресепшен", route_judge: "Судья на трассе" };
  return <details className="admin-user-menu" ref={ref}>
    <summary aria-label={`Меню пользователя: ${user.full_name}`}><span className="admin-user-avatar"><UserRound size={23}/></span><span className="admin-user-copy"><strong>{user.full_name}</strong><small>{roles[user.role] ?? user.role}</small></span><ChevronDown className="admin-user-chevron" size={17}/></summary>
    <div className="admin-user-dropdown">
      <button onClick={() => run(onGuide)}><BookOpen size={16}/>Инструкция по роли</button>
      {onSettings && <button onClick={() => run(onSettings)}><Settings size={16}/>Настройки</button>}
      <button className="admin-user-logout" onClick={() => run(onLogout)}><LogOut size={16}/>Выйти</button>
    </div>
  </details>;
}
