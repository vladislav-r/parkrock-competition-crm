import Link from "next/link";
import { groupSlug } from "@/lib/api";

export default function ResultsNavigation({ groups, active }: { groups: string[]; active: string }) {
  return <nav className="category-tabs" aria-label="Возрастные категории">
    <Link href="/absolute" className={active === "absolute" ? "active" : ""} aria-current={active === "absolute" ? "page" : undefined}>Абсолют</Link>
    <Link href="/teams" className={active === "teams" ? "active" : ""} aria-current={active === "teams" ? "page" : undefined}>Командный зачёт</Link>
    {groups.map((name) => <Link key={name} href={`/results/${groupSlug(name)}`} className={active === groupSlug(name) ? "active" : ""} aria-current={active === groupSlug(name) ? "page" : undefined}>{name}</Link>)}
  </nav>;
}
