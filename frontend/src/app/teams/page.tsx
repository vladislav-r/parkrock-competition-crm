"use client";

import Link from "next/link";
import PublicHeader from "../components/PublicHeader";
import { useEffect, useState } from "react";
import { ChevronLeft } from "lucide-react";
import { getPublicResults } from "@/lib/api";
import ResultsNavigation from "../components/ResultsNavigation";
import SponsorStrip from "../components/SponsorStrip";

export default function TeamsPage() {
  const [groups, setGroups] = useState<string[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    getPublicResults().then(data => { if (active) setGroups(data.groups); }).catch(() => { if (active) setError("Не удалось загрузить список категорий. Вернитесь к категориям или обновите страницу."); });
    return () => { active = false; };
  }, []);
  return <main className="public-page qualification-page sand-theme sand-secondary">
    <div className="sand-frame"><PublicHeader />
    <section className="results-shell qualification-shell">
      <ResultsNavigation groups={groups} active="teams"/>
      <div className="qualification-heading"><div><div className="eyebrow">Боулдеринг · командный зачёт</div><h2>Командный зачёт</h2></div></div>
      <div className="qualification-table-wrap"><div className="empty-state"><h3>Скоро 😉</h3></div></div>
      {error && <div className="error-banner">{error}</div>}
    </section></div><footer className="sand-footer"><SponsorStrip /></footer>
  </main>;
}
