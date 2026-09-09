"use client";

import Link from "next/link";
import SponsorStrip from "@/app/components/SponsorStrip";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Check,
  ChevronRight,
  Clock3,
  Mountain,
  Trophy,
  Users,
} from "lucide-react";
import { getPublicResults, groupSlug, PublicResults } from "@/lib/api";

function categoryBadge(name: string) {
  const [label, range] = name.split(/\s+/, 2);
  return `${label.slice(0, 1)}${range ? ` ${range}` : ""}`;
}

export default function FestivalPage() {
  const [data, setData] = useState<PublicResults | null>(null);
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      setData(await getPublicResults());
      setError("");
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Не удалось загрузить фестиваль",
      );
    }
  }, []);
  useEffect(() => {
    load();
    const timer = window.setInterval(load, 5000);
    return () => window.clearInterval(timer);
  }, [load]);

  const categories = useMemo(
    () =>
      data?.groups.map((name) => {
        const participants = data.results.filter(
          (row) => row.group_name === name,
        );
        return {
          name,
          total: participants.length,
          withResult: participants.filter((row) => row.has_result).length,
          finalOpen: data.final_groups.includes(name),
        };
      }) ?? [],
    [data],
  );
  const resultCount = data?.results.filter((row) => row.has_result).length ?? 0;
  const beforeFinal =
    data?.stage === "preparation" || data?.stage === "qualification";

  return (
    <main className="festival-page public-results-page">
      <header className="public-header">
        <img
          className="brand-logo public-brand-logo"
          src="/brand/parkrock-black.svg"
          alt="ПаркРок"
        />
        <div>
          <div className="eyebrow">Онлайн-результаты</div>
          <h1>Парк Рок: Каменный век</h1>
        </div>
        <div className="public-nav">
          <span className="public-header-status">
            <Clock3 size={14} />
            Обновляется автоматически
          </span>
          <Link href="/sets">Сеты</Link>
        </div>
      </header>
      <SponsorStrip />
      <section className="public-results-board">
        <div className="discipline-title">
          <span>
            <Mountain size={25} />
          </span>
          <div>
            <div className="eyebrow">Дисциплина</div>
            <h2>Боулдеринг</h2>
          </div>
          <div className="public-totals">
            <span>
              <Users size={16} />
              <b>{data?.results.length ?? 0}</b> участников
            </span>
            <span>
              <Trophy size={16} />
              <b>{resultCount}</b> с результатом
            </span>
          </div>
        </div>
        <div className="public-stage-flow">
          <div
            className={`public-stage ${data?.stage === "preparation" ? "pending" : "active"}`}
          >
            <span>
              <Check size={16} />
            </span>
            <div>
              <strong>Квалификация</strong>
              <small>
                {data?.stage === "preparation"
                  ? "Ещё не начата"
                  : "Результаты по всем трассам"}
              </small>
            </div>
          </div>
          <ChevronRight />
          <div className={`public-stage ${beforeFinal ? "pending" : "active"}`}>
            <span>{beforeFinal ? "2" : <Check size={16} />}</span>
            <div>
              <strong>Финал</strong>
              <small>
                {beforeFinal
                  ? "Будет открыт после квалификации"
                  : "Результаты финала доступны"}
              </small>
            </div>
          </div>
        </div>
        {error && <div className="error-banner">{error}</div>}
        <div className="public-category-heading">
          <div>
            <div className="eyebrow">Возрастные категории</div>
            <h2>Выберите свою группу</h2>
          </div>
          <p>
            Откройте квалификационную таблицу, чтобы посмотреть места и
            результаты по трассам.
          </p>
        </div>
        <div className="public-category-grid">
          {categories.map((category) => (
            <Link
              key={category.name}
              href={`/results/${groupSlug(category.name)}`}
              className={`public-category-card${category.finalOpen ? " final-open" : ""}`}
            >
              <span className="category-card-icon" aria-hidden="true">
                {categoryBadge(category.name)}
              </span>
              <span className="category-card-main">
                <strong>{category.name}</strong>
                <small>
                  {category.finalOpen
                    ? "Финал открыт · порядок выхода опубликован"
                    : `${category.total} участников · ${category.withResult} с результатом`}
                </small>
              </span>
              {category.finalOpen && (
                <span className="category-final-chip">
                  <Trophy size={13} />
                  Финал
                </span>
              )}
              <ChevronRight size={21} />
            </Link>
          ))}
        </div>
        {!categories.length && !error && (
          <div className="empty-state">Загружаем возрастные категории...</div>
        )}
      </section>
    </main>
  );
}
