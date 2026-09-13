"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { groupSlug } from "@/lib/api";

export default function ResultsNavigation({ groups, active, compact = false }: { groups: string[]; active: string; compact?: boolean }) {
  const router = useRouter();
  if (compact) return <nav className="sand-group-switch" aria-label="Возрастные категории">
    <Link href="/">← Все категории</Link>
    <label><span className="sand-sr-only">Сменить категорию</span><select value={groups.some(name => groupSlug(name) === active) ? active : ""} onChange={event => router.push(`/results/${event.target.value}`)}>
      <option value="" disabled>Выберите категорию</option>
      {groups.map(name => <option key={name} value={groupSlug(name)}>{name}</option>)}
    </select></label>
  </nav>;
  return <nav className="category-tabs" aria-label="Возрастные категории">
    <Link href="/tv">Режим ТВ</Link>
    <Link href="/absolute" className={active === "absolute" ? "active" : ""} aria-current={active === "absolute" ? "page" : undefined}>Абсолют</Link>
    <Link href="/teams" className={active === "teams" ? "active" : ""} aria-current={active === "teams" ? "page" : undefined}>Командный зачёт</Link>
    {groups.map((name) => <Link key={name} href={`/results/${groupSlug(name)}`} className={active === groupSlug(name) ? "active" : ""} aria-current={active === groupSlug(name) ? "page" : undefined}>{name}</Link>)}
  </nav>;
}
