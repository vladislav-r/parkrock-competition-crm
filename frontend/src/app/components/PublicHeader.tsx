"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function PublicHeader() {
  const pathname = usePathname();
  return <header className="sand-header">
    <Link href="/" className="sand-brand" aria-label="ПаркРок — все категории">
      <img src="/brand/parkrock-white.svg" alt="Парк Рок: Каменный век" width={220} height={47} />
    </Link>
    <nav className="sand-navigation" aria-label="Основная навигация">
      <Link href="/" aria-current={pathname === "/" || pathname.startsWith("/results/") ? "page" : undefined}>Категории</Link><Link href="/absolute" aria-current={pathname === "/absolute" ? "page" : undefined}>Абсолют</Link><Link href="/sets" aria-current={pathname === "/sets" ? "page" : undefined}>Сеты</Link>
    </nav>
    <details className="sand-menu"><summary aria-label="Другие разделы"><span aria-hidden="true">☰</span></summary>
      <nav aria-label="Другие разделы"><Link href="/">Все категории</Link><Link href="/absolute">Абсолютный зачёт</Link><Link href="/sets">Сеты</Link><Link href="/teams">Командный зачёт</Link><Link href="/tv">Режим ТВ</Link></nav>
    </details>
  </header>;
}
