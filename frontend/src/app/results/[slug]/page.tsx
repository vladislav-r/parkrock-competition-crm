"use client";

import Link from "next/link";
import SponsorStrip from "@/app/components/SponsorStrip";
import ResultsNavigation from "@/app/components/ResultsNavigation";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Medal,
  RefreshCw,
  Trophy,
  X,
} from "lucide-react";
import {
  getPublicFinalResults,
  getPublicParticipant,
  getPublicResults,
  groupSlug,
  Medal as MedalType,
  PublicFinalResults,
  PublicParticipant,
  PublicResults,
} from "@/lib/api";

const MEDAL_LABELS: Record<MedalType, string> = {
  gold: "Золото",
  silver: "Серебро",
  bronze: "Бронза",
};
function FinisherMedal({ medal }: { medal: MedalType }) {
  return (
    <span
      className={`finisher-medal ${medal}`}
      title={`Финишер · ${MEDAL_LABELS[medal]}`}
    >
      <Medal size={20} />
      <small>{MEDAL_LABELS[medal]}</small>
    </span>
  );
}

export default function CategoryResultsPage() {
  const params = useParams<{ slug: string }>();
  const [data, setData] = useState<PublicResults | null>(null);
  const [finalData, setFinalData] = useState<PublicFinalResults | null>(null);
  const [view, setView] = useState<"qualification" | "final">("qualification");
  const initialFinalViewForSlug = useRef<string | null>(null);
  const [detail, setDetail] = useState<PublicParticipant | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const publicData = await getPublicResults();
      setData(publicData);
      setError("");
      const selectedGroup = publicData.groups.find(
        (name) => groupSlug(name) === params.slug,
      );
      if (
        selectedGroup &&
        (publicData.stage === "final" || publicData.stage === "completed") &&
        publicData.final_groups.includes(selectedGroup)
      ) {
        try {
          setFinalData(await getPublicFinalResults(selectedGroup));
          if (initialFinalViewForSlug.current !== params.slug) {
            setView("final");
            initialFinalViewForSlug.current = params.slug;
          }
        } catch {
          setFinalData(null);
          setView("qualification");
        }
      } else {
        setFinalData(null);
        setView("qualification");
      }
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Не удалось загрузить результаты",
      );
    }
  }, [params.slug]);

  useEffect(() => {
    setView("qualification");
    initialFinalViewForSlug.current = null;
  }, [params.slug]);
  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 3000);
    return () => window.clearInterval(timer);
  }, [load]);
  useEffect(() => {
    if (!detail) return;
    const previousOverflow = document.body.style.overflow;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setDetail(null);
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [detail]);

  const group = data?.groups.find((name) => groupSlug(name) === params.slug);
  const rows = useMemo(
    () => data?.results.filter((row) => row.group_name === group) ?? [],
    [data, group],
  );
  const isFinalView = view === "final" && finalData !== null;

  async function openParticipant(id: string) {
    try {
      setDetail(await getPublicParticipant(id));
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Не удалось открыть участника",
      );
    }
  }

  return (
    <main className="public-page qualification-page">
      <header className="public-header">
        <Link href="/" className="header-back" title="К категориям">
          <ChevronLeft size={22} />
        </Link>
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
      <section className="results-shell qualification-shell">
        <ResultsNavigation groups={data?.groups ?? []} active={params.slug}/>
        <div className="qualification-heading">
          <div>
            <div className="eyebrow">
              Боулдеринг · {isFinalView ? "этап 2 из 2" : "этап 1 из 2"}
            </div>
            <h2>{group ?? (data ? "Категория не найдена" : "Загрузка...")}</h2>
            <p>
              {isFinalView ? (
                <>
                  <span className="qualification-badge final">
                    <Trophy size={14} />
                    Финал
                  </span>
                  {finalData.results.length} финалистов ·{" "}
                  {finalData.routes.length
                    ? `${finalData.routes.length} трассы`
                    : "трассы назначаются"}
                </>
              ) : (
                <>
                  <span className="qualification-badge">
                    <Check size={14} />
                    Квалификация
                  </span>
                  {rows.length} участников ·{" "}
                  {rows.filter((row) => row.has_result).length} с результатом
                </>
              )}
            </p>
          </div>
          <button
            className="icon-button"
            onClick={() => void load()}
            title="Обновить"
          >
            <RefreshCw size={18} />
          </button>
        </div>
        {error && <div className="error-banner">{error}</div>}
        <div className="stage-view-tabs">
          <button
            className={!isFinalView ? "active" : ""}
            onClick={() => setView("qualification")}
          >
            Квалификация
          </button>
          {finalData && (
            <button
              className={isFinalView ? "active final" : ""}
              onClick={() => setView("final")}
            >
              Финал
            </button>
          )}
        </div>
        {isFinalView ? (
          <PublicFinalTable data={finalData} />
        ) : (
          <>
            <div className="qualification-table-wrap">
              <table className="qualification-table compact">
                <thead>
                  <tr>
                    <th>Место</th>
                    <th className="start-number-column">Ст. №</th>
                    <th>Участник</th>
                    <th>Клуб</th>
                    <th>Очки</th>
                    {data?.details_enabled && (
                      <th className="open-column" aria-label="Открыть" />
                    )}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr
                      key={row.participant_id}
                      className={[
                        row.is_finalist ? "finalist" : "",
                        data?.details_enabled ? "details-enabled" : "",
                      ]
                        .filter(Boolean)
                        .join(" ")}
                      onClick={
                        data?.details_enabled
                          ? () => void openParticipant(row.participant_id)
                          : undefined
                      }
                    >
                      <td>
                        {row.place !== null && (
                          <>
                            {row.medal ? (
                              <FinisherMedal medal={row.medal} />
                            ) : (
                              <strong>{row.place}</strong>
                            )}
                          </>
                        )}
                      </td>
                      <td className="start-number-column">
                        <span className="bib">{row.start_number}</span>
                      </td>
                      <td className="athlete-name">
                        <strong>{row.full_name}</strong>
                      </td>
                      <td className="club" title={row.club}>
                        {row.club}
                      </td>
                      <td className="qualification-total">
                        <strong>
                          {row.points?.toLocaleString("ru-RU") ?? "—"}
                        </strong>
                      </td>
                      {data?.details_enabled && (
                        <td className="open-column">
                          <ChevronRight size={18} />
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
              {data && group && !rows.length && (
                <div className="empty-state">
                  В этой категории пока нет заявленных участников.
                </div>
              )}
            </div>
            {data?.details_enabled && (
              <p className="qualification-legend">
                Нажмите на участника, чтобы открыть подробный результат.
              </p>
            )}
          </>
        )}
      </section>
      {detail && (
        <ParticipantDetail detail={detail} onClose={() => setDetail(null)} />
      )}
    </main>
  );
}

function PublicFinalTable({ data }: { data: PublicFinalResults }) {
  const waitingForFirstResult =
    data.results.length > 0 && data.results.every((row) => !row.has_result);
  return (
    <>
      {waitingForFirstResult && (
        <div className="final-start-order-note">
          <Clock3 size={18} />
          <div>
            <strong>Порядок выхода опубликован</strong>
            <span>
              Финалисты показаны по возрастанию номера выхода. Результаты
              появятся здесь после первых стартов.
            </span>
          </div>
        </div>
      )}
      <div className="final-public-table-wrap">
        <table className="final-public-table">
          <thead>
            <tr>
              <th>Место</th>
              <th>
                <span className="desktop-column-label">Выход</span>
                <span className="mobile-column-label">Вых.</span>
              </th>
              <th>Ст. №</th>
              <th>Участник</th>
              <th>Клуб</th>
              <th>Квал.</th>
              {data.routes.map((route) => (
                <th
                  key={route.number}
                  className="final-route-head"
                  title={route.name}
                >
                  <span>{route.number}</span>
                  <small>{route.name}</small>
                </th>
              ))}
              <th>Т / З</th>
              <th>Итог</th>
            </tr>
          </thead>
          <tbody>
            {data.results.map((row) => (
              <tr
                key={row.participant_id}
                className={row.has_result ? "has-result" : "waiting-result"}
              >
                <td>
                  {row.place !== null && row.place <= 3 ? (
                    <span
                      className={`final-place place-${row.place}`}
                      title={`${row.place} место`}
                    >
                      {row.place}
                    </span>
                  ) : (
                    row.place ?? "—"
                  )}
                </td>
                <td className="exit-order-cell">{row.exit_order ?? "—"}</td>
                <td>
                  <span className="bib">{row.start_number}</span>
                </td>
                <td className="athlete-name">
                  <strong>{row.full_name}</strong>
                </td>
                <td className="club" title={row.club}>
                  {row.club}
                </td>
                <td>{row.qualification_place}</td>
                {data.routes.map((route) => {
                  const attempt = row.attempts.find(
                    (item) => item.route_number === route.number,
                  );
                  return (
                    <td key={route.number} className="final-attempt-cell">
                      <span
                        className={
                          attempt?.top_attempt
                            ? "attempt-top filled"
                            : "attempt-top"
                        }
                      >
                        {attempt?.top_attempt ?? ""}
                      </span>
                      <span
                        className={
                          attempt?.zone_attempt
                            ? "attempt-zone filled"
                            : "attempt-zone"
                        }
                      >
                        {attempt?.zone_attempt ?? ""}
                      </span>
                    </td>
                  );
                })}
                <td className="final-counts">
                  <b>{row.top_count}</b> / <b>{row.zone_count}</b>
                </td>
                <td className="final-score">
                  {row.score.toLocaleString("ru-RU", {
                    minimumFractionDigits: 0,
                    maximumFractionDigits: 1,
                  })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!data.results.length && (
          <div className="empty-state">В этой категории нет финалистов.</div>
        )}
      </div>
    </>
  );
}

function ParticipantDetail({
  detail,
  onClose,
}: {
  detail: PublicParticipant;
  onClose: () => void;
}) {
  return (
    <div
      className="modal-backdrop participant-detail-backdrop"
      role="presentation"
      onMouseDown={onClose}
    >
      <article
        className="modal participant-detail-modal"
        role="dialog"
        aria-modal="true"
        aria-label={`Результат ${detail.full_name}`}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button className="modal-close" onClick={onClose} title="Закрыть">
          <X />
        </button>
        <div className="eyebrow">Стартовый номер {detail.start_number}</div>
        <h2>{detail.full_name}</h2>
        <p className="muted">
          {detail.club} · {detail.group_name}
        </p>
        {detail.has_result ? (
          <>
            <div className="score-strip">
              <div>
                <span>{detail.medal ? "Финишер" : "Место"}</span>
                <strong>
                  {detail.medal ? (
                    <FinisherMedal medal={detail.medal} />
                  ) : (
                    (detail.place ?? "")
                  )}
                </strong>
              </div>
              <div>
                <span>Очки</span>
                <strong>{detail.points?.toLocaleString("ru-RU") ?? ""}</strong>
              </div>
            </div>
            {detail.is_finalist && (
              <div className="participant-finalist-note">
                <Trophy size={15} />
                Также участник прошёл в финал по квалификационному рейтингу.
              </div>
            )}
            <h3>Пройденные трассы</h3>
            <div className="route-list">
              {detail.completed_routes.map((route) => (
                <div key={route.number}>
                  <span className="route-number">{route.number}</span>
                  <span>
                    {route.name}
                    <small>{route.grade}</small>
                  </span>
                  <strong>{route.points}</strong>
                </div>
              ))}
            </div>
          </>
        ) : (
          <div className="public-waiting">
            <Clock3 size={22} />
            <div>
              <strong>Результат пока не зафиксирован</strong>
              <p>Участник заявлен, но ещё не прошёл ни одной трассы.</p>
            </div>
          </div>
        )}
      </article>
    </div>
  );
}
