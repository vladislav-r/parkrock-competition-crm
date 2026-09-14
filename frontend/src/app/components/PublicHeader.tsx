"use client";

import Link from "next/link";
import { useEffect } from "react";
import { usePathname } from "next/navigation";

export default function PublicHeader() {
  const pathname = usePathname();
  useEffect(() => {
    const page = document.querySelector<HTMLElement>(".sand-theme");
    if (!page) return;
    let frame = 0;
    let previous = "";
    const update = () => {
      frame = 0;
      const artworkHeight = Math.max(window.innerHeight, window.innerWidth * 1024 / 1536);
      const offset = `${-Math.min(Math.max(0, window.scrollY), artworkHeight - window.innerHeight)}px`;
      if (offset !== previous) { page.style.setProperty("--sand-background-offset", offset); previous = offset; }
    };
    const schedule = () => { if (!frame) frame = requestAnimationFrame(update); };
    update();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    return () => { cancelAnimationFrame(frame); window.removeEventListener("scroll", schedule); window.removeEventListener("resize", schedule); page.style.removeProperty("--sand-background-offset"); };
  }, [pathname]);
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
