"use client";

import Link from "next/link";
import SponsorStrip from "@/app/components/SponsorStrip";
import PublicHeader from "@/app/components/PublicHeader";
import { publicRefreshMs, usePublicRefresh } from "@/lib/public-refresh";
import { useCallback, useEffect, useState } from "react";
import { ChevronRight, Trophy } from "lucide-react";
import { getPublicResults, groupSlug, PublicResults } from "@/lib/api";

export default function FestivalPage() {
  const [data, setData] = useState<PublicResults | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try { setData(await getPublicResults()); setError(""); }
    catch (e) { setError(e instanceof Error ? e.message : "Не удалось загрузить фестиваль"); }
  }, []);
  usePublicRefresh(load, publicRefreshMs(data, data?.stage ?? "qualification"));
  const categories = data?.groups.map(name => ({ name,
    total: data.results.filter(row => row.group_name === name).length,
    female: /^(Ж|Дев)/i.test(name),
    age: name.match(/\d+\s*[–-]\s*\d+/)?.[0].replace(/\s*-\s*/, "–") ?? (/^(Мужчины|Женщины)$/i.test(name) ? "19+" : name),
  })) ?? [];
  return <main className="sand-theme sand-home">
    <div className="sand-frame"><PublicHeader />
      <section className="sand-directory" aria-labelledby="directory-title">
        <div className="sand-title"><h1 id="directory-title">Онлайн-результаты</h1><p>Боулдеринг · ПаркРок: Каменный век</p></div>
        {error && <div className="error-banner" role="alert">{error}<button onClick={load}>Повторить</button></div>}
        <div className="sand-categories">
          {[true, false].map(female => <section className="sand-category-column" key={String(female)} aria-label={female ? "Женские категории" : "Мужские категории"}>
            <h2><span aria-hidden="true">{female ? "♀" : "♂"}</span>{female ? "Женщины" : "Мужчины"}</h2>
            {categories.filter(category => category.female === female).map(category => <Link href={`/results/${groupSlug(category.name)}`} key={category.name} className="sand-category" aria-label={`${category.name}, участников: ${category.total}`}>
              <strong>{category.age === "19+" ? <>19<span className="sand-adult-long"> лет и старше</span><span className="sand-adult-short">+</span></> : <>{category.age} <span>лет</span></>}</strong>
              <small>{category.total}<span> {new Intl.PluralRules("ru").select(category.total) === "one" ? "участник" : new Intl.PluralRules("ru").select(category.total) === "few" ? "участника" : "участников"}</span></small><ChevronRight size={16} />
            </Link>)}
          </section>)}
        </div>
        {!data && !error && <p className="sand-empty" role="status">Загружаем категории…</p>}
        {data && !categories.length && <p className="sand-empty">Возрастные категории пока не опубликованы.</p>}
        <Link href="/absolute" className="sand-absolute"><Trophy size={26}/><span><strong>Абсолютный зачёт</strong><small>Все участники · женщины и мужчины</small></span><span className="sand-absolute-count">{data?.results.length ?? "—"}</span><ChevronRight size={20}/></Link>
        <p className="sand-live">{data?.stage === "preparation" ? "Квалификация ещё не началась" : data?.stage === "completed" ? "Соревнование завершено" : "Результаты обновляются автоматически"}</p>
      </section><div className="sand-camp" aria-hidden="true" />
    </div>
    <footer className="sand-footer"><SponsorStrip /></footer>
  </main>;
}
