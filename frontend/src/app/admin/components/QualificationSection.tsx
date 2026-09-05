"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Archive,
  Check,
  CheckCircle2,
  CircleAlert,
  Download,
  Eye,
  Flag,
  LayoutDashboard,
  RotateCcw,
  ShieldCheck,
  Trophy,
  X,
} from "lucide-react";
import {
  cancelQualification,
  confirmAllQualificationCategories,
  confirmQualificationCategory,
  downloadProtocolXlsx,
  FinalStatus,
  getFinalStatus,
  getQualificationCategoryResults,
  QualificationCategoryReview,
  reopenAllQualificationCategories,
  reopenQualificationCategory,
  startQualification,
} from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";

type Category = FinalStatus["categories"][number];
type View = "overview" | "exports";
type Pending =
  | { type: "start" }
  | { type: "cancel" }
  | { type: "confirm-all" }
  | { type: "reopen-all" }
  | { type: "confirm"; category: Category }
  | { type: "reopen"; category: Category };

export function QualificationSection({
  token,
  canExport,
  onUpdated,
}: {
  token: string;
  canExport: boolean;
  onUpdated: () => Promise<void>;
}) {
  const [status, setStatus] = useState<FinalStatus | null>(null);
  const [view, setView] = useState<View>("overview");
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reviewCategory, setReviewCategory] = useState<Category | null>(null);
  const [review, setReview] = useState<QualificationCategoryReview | null>(
    null,
  );
  const [downloadingId, setDownloadingId] = useState("");

  async function download(category: Category) {
    setDownloadingId(category.id);
    try {
      await downloadProtocolXlsx(token, "qualification", category.id, category.name);
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось скачать протокол");
    } finally {
      setDownloadingId("");
    }
  }

  const load = useCallback(async () => {
    try {
      setStatus(await getFinalStatus(token));
      setError("");
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Не удалось загрузить квалификацию",
      );
    }
  }, [token]);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(), 3000);
    return () => window.clearInterval(timer);
  }, [load]);

  async function applyAction() {
    if (!pending || !status) return;
    setBusy(true);
    try {
      const next =
        pending.type === "start"
          ? await startQualification(token, status.event_version)
          : pending.type === "cancel"
            ? await cancelQualification(token, status.event_version)
            : pending.type === "confirm-all"
              ? await confirmAllQualificationCategories(
                  token,
                  status.event_version,
                )
              : pending.type === "reopen-all"
                ? await reopenAllQualificationCategories(
                    token,
                    status.event_version,
                  )
                : pending.type === "confirm"
                  ? await confirmQualificationCategory(
                      token,
                      pending.category.id,
                      pending.category.expected_version,
                    )
                  : await reopenQualificationCategory(
                      token,
                      pending.category.id,
                      pending.category.expected_version,
                    );
      setStatus(next);
      setPending(null);
      setReviewCategory(null);
      setReview(null);
      setError("");
      await onUpdated();
    } catch (reason) {
      setPending(null);
      setError(
        reason instanceof Error ? reason.message : "Действие не выполнено",
      );
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function openReview(category: Category) {
    setReviewCategory(category);
    setReview(null);
    try {
      setReview(await getQualificationCategoryResults(token, category.id));
    } catch (reason) {
      setReviewCategory(null);
      setError(
        reason instanceof Error
          ? reason.message
          : "Не удалось загрузить результаты категории",
      );
    }
  }

  if (!status)
    return (
      <section className="qualification-workspace">
        <div className="final-loading">Загрузка квалификации…</div>
        {error && <div className="error-banner">{error}</div>}
      </section>
    );
  const confirmedCount = status.categories.filter(
    (item) => item.confirmed,
  ).length;
  const started = Boolean(status.qualification_started_at);
  const qualificationOpen = status.stage === "qualification";
  const groupsWithoutResults = status.categories
    .filter((category) => category.result_count === 0)
    .map((category) => category.name);
  const emptyResultsWarning = groupsWithoutResults.length
    ? `По возрастным группам «${groupsWithoutResults.join("», «")}» ещё нет результатов. Вы уверены?`
    : "";
  const pendingCopy =
    pending?.type === "start"
      ? {
          title: "Начать квалификацию?",
          description:
            "Перед переходом система создаст проверенную резервную копию. После запуска станет доступен ввод результатов участников.",
          label: "Начать квалификацию",
          danger: false,
        }
      : pending?.type === "cancel"
        ? {
            title: "Отменить квалификацию?",
            description:
              "Сначала система сохранит текущее состояние, затем вернётся к снимку перед запуском квалификации. Результаты квалификации останутся доступны в резервной копии.",
            label: "Отменить квалификацию",
            danger: true,
          }
        : pending?.type === "confirm-all"
          ? {
              title: "Подтвердить всю квалификацию?",
              description:
                emptyResultsWarning ||
                "Текущие результаты и состав финалистов всех возрастных групп будут отмечены как проверенные.",
              label: "Подтвердить все группы",
              danger: Boolean(emptyResultsWarning),
            }
          : pending?.type === "reopen-all"
            ? {
                title: "Отменить подтверждение квалификации?",
                description:
                  "Подтверждение будет снято со всех возрастных групп. Результаты сохранятся и их можно будет проверить повторно.",
                label: "Снять подтверждение",
                danger: true,
              }
            : pending?.type === "confirm"
              ? {
                  title: `Подтвердить «${pending.category.name}»?`,
                  description:
                    pending.category.result_count === 0
                      ? `По возрастной группе «${pending.category.name}» ещё нет результатов. Вы уверены?`
                      : "Текущие места и список финалистов будут отмечены как проверенные.",
                  label: "Подтвердить результаты",
                  danger: pending.category.result_count === 0,
                }
              : {
                  title: `Снять подтверждение «${pending?.category.name}»?`,
                  description:
                    "Группу потребуется проверить и подтвердить повторно перед запуском финала.",
                  label: "Снять подтверждение",
                  danger: false,
                };

  return (
    <section className="final-workspace qualification-workspace">
      <header className="admin-section-hero">
        <div>
          <div className="eyebrow">Этап соревнования</div>
          <h1>{!started ? "Подготовка" : "Квалификация"}</h1>
          <p>
            {!started
              ? "Подготовка продолжается. Прибытие и работа с участниками доступны, ввод результатов пока закрыт."
              : qualificationOpen
                ? "Вносите результаты, проверяйте возрастные группы и подтвердите квалификацию перед финалом."
                : "Квалификационные результаты зафиксированы и доступны для просмотра."}
          </p>
        </div>
        <div
          className={`section-health ${started ? status.stage : "preparation"}`}
        >
          <Flag size={22} />
          <span>
            <strong>
              {!started
                ? "Готово"
                : `${confirmedCount}/${status.categories.length}`}
            </strong>
            <small>{!started ? "к запуску" : "групп подтверждено"}</small>
          </span>
        </div>
      </header>
      <div className="final-content-grid">
        <aside className="final-sidebar">
          <span className="eyebrow">Квалификация</span>
          <button
            className={view === "overview" ? "active" : ""}
            onClick={() => setView("overview")}
          >
            <LayoutDashboard size={17} />
            Результаты
          </button>
          <button
            className={view === "exports" ? "active" : ""}
            onClick={() => setView("exports")}
          >
            <Download size={17} />
            Выгрузка
          </button>
        </aside>
        <div className="final-pane">
          {error && <div className="error-banner compact">{error}</div>}
          {view === "overview" && (
            <>
              {!started && (
                <div className="qualification-start-card">
                  <span className="qualification-start-icon">
                    <ShieldCheck size={24} />
                  </span>
                  <div>
                    <strong>Фестиваль ещё не начат</strong>
                    <small>
                      До запуска можно принимать участников и готовить данные.
                      Отметки прохождения трасс откроются после подтверждения.
                    </small>
                  </div>
                  <button
                    className="primary-action"
                    onClick={() => setPending({ type: "start" })}
                  >
                    <Flag size={17} />
                    Начать квалификацию
                  </button>
                </div>
              )}
              {started && (
                <div className="final-progress">
                  <span>
                    <strong>
                      {confirmedCount}/{status.categories.length}
                    </strong>
                    <small>возрастных групп подтверждено</small>
                  </span>
                  <div>
                    <i
                      style={{
                        width: `${status.categories.length ? (confirmedCount / status.categories.length) * 100 : 0}%`,
                      }}
                    />
                  </div>
                  {qualificationOpen && (
                    <span className="qualification-progress-actions">
                      <button
                        className="danger-outline-button confirm-all-button"
                        onClick={() => setPending({ type: "cancel" })}
                      >
                        <RotateCcw size={16} />
                        Отменить квалификацию
                      </button>
                      {confirmedCount > 0 && (
                        <button
                          className="secondary-button confirm-all-button"
                          onClick={() => setPending({ type: "reopen-all" })}
                        >
                          <RotateCcw size={16} />
                          Снять подтверждение
                        </button>
                      )}
                      <button
                        className="secondary-button confirm-all-button"
                        disabled={status.all_categories_confirmed}
                        onClick={() => setPending({ type: "confirm-all" })}
                      >
                        <CheckCircle2 size={16} />
                        {status.all_categories_confirmed
                          ? "Всё подтверждено"
                          : "Подтвердить квалификацию"}
                      </button>
                    </span>
                  )}
                </div>
              )}
              <div className="qualification-category-list">
                {status.categories.map((category) => (
                  <article
                    key={category.id}
                    className={
                      category.confirmed
                        ? "qualification-category confirmed"
                        : "qualification-category"
                    }
                  >
                    <span className="qualification-status-icon">
                      {category.confirmed ? (
                        <CheckCircle2 size={21} />
                      ) : (
                        <CircleAlert size={21} />
                      )}
                    </span>
                    <div>
                      <strong>{category.name}</strong>
                      <small>
                        {category.result_count} результатов ·{" "}
                        {category.participates_in_final
                          ? `${category.finalist_count} финалистов`
                          : "без финала · финишеры по медалям"}
                      </small>
                    </div>
                    <span className="qualification-category-actions">
                      <button
                        className="secondary-button compact-action"
                        onClick={() => void openReview(category)}
                      >
                        <Eye size={14} />
                        Просмотреть
                      </button>
                      {started &&
                        qualificationOpen &&
                        (category.confirmed ? (
                          <button
                            className="secondary-button compact-action"
                            onClick={() =>
                              setPending({ type: "reopen", category })
                            }
                          >
                            <RotateCcw size={14} />
                            Снять
                          </button>
                        ) : (
                          <button
                            className="confirm-results-button"
                            onClick={() =>
                              setPending({ type: "confirm", category })
                            }
                          >
                            <Check size={15} />
                            Подтвердить
                          </button>
                        ))}
                    </span>
                  </article>
                ))}
              </div>
            </>
          )}
          {view === "exports" && (
            <section className="final-exports">
              <div className="final-panel-heading">
                <div>
                  <span className="eyebrow">Протоколы квалификации</span>
                  <h2>Выгрузка по возрастным группам</h2>
                  <p>
                    Файл формируется по подтверждённым результатам категории.
                  </p>
                </div>
                <Download size={22} />
              </div>
              <div>
                {status.categories.map((category) => (
                  <button
                    key={category.id}
                    disabled={!canExport || !category.confirmed || Boolean(downloadingId)}
                    title={
                      !canExport
                        ? "Недостаточно прав на формирование выгрузок"
                        : !category.confirmed
                          ? "Сначала подтвердите результаты категории"
                          : "Скачать итоговый протокол квалификации"
                    }
                    onClick={() => void download(category)}
                  >
                    <Download size={16} />
                    <span>
                      <strong>{category.name}</strong>
                      <small>{downloadingId === category.id ? "Формируем…" : "XLSX"}</small>
                    </span>
                  </button>
                ))}
              </div>
            </section>
          )}
          {reviewCategory && (
            <div
              className="modal-backdrop"
              role="presentation"
              onMouseDown={() => {
                setReviewCategory(null);
                setReview(null);
              }}
            >
              <section
                className="qualification-review-dialog"
                role="dialog"
                aria-modal="true"
                aria-labelledby="qualification-review-title"
                onMouseDown={(event) => event.stopPropagation()}
              >
                <button
                  className="dialog-close"
                  onClick={() => {
                    setReviewCategory(null);
                    setReview(null);
                  }}
                  title="Закрыть"
                >
                  <X size={18} />
                </button>
                <div className="dialog-icon">
                  <Trophy size={22} />
                </div>
                <div className="eyebrow">Результаты квалификации</div>
                <h2 id="qualification-review-title">{reviewCategory.name}</h2>
                {!review && (
                  <div className="final-loading">Загружаем результаты…</div>
                )}
                {review && (
                  <>
                    <div className="qualification-review-summary">
                      <span>
                        <strong>{review.results.length}</strong>
                        <small>с результатом</small>
                      </span>
                      <span>
                        <strong>
                          {reviewCategory.participates_in_final
                            ? review.results.filter((item) => item.is_finalist)
                                .length
                            : "—"}
                        </strong>
                        <small>
                          {reviewCategory.participates_in_final
                            ? "проходят в финал"
                            : "категория без финала"}
                        </small>
                      </span>
                    </div>
                    <div className="qualification-review-table-wrap">
                      <table className="qualification-review-table">
                        <thead>
                          <tr>
                            <th>Место</th>
                            <th>№</th>
                            <th>Участник</th>
                            <th>Клуб</th>
                            <th>Трассы</th>
                            <th>Очки</th>
                            <th>Статус</th>
                          </tr>
                        </thead>
                        <tbody>
                          {review.results.map((item) => (
                            <tr
                              key={item.participant_id}
                              className={
                                item.is_finalist ? "review-finalist" : ""
                              }
                            >
                              <td>
                                <strong>{item.place}</strong>
                              </td>
                              <td>{item.start_number}</td>
                              <td>{item.full_name}</td>
                              <td>{item.club}</td>
                              <td>{item.completed_count}</td>
                              <td>
                                <strong>{item.points}</strong>
                              </td>
                              <td>
                                {item.is_finalist ? (
                                  <span className="review-finalist-badge">
                                    <Trophy size={13} />
                                    Финалист
                                  </span>
                                ) : (
                                  "—"
                                )}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {!review.results.length && (
                        <div className="qualification-review-empty">
                          В группе пока нет участников с результатом.
                        </div>
                      )}
                    </div>
                    <div className="dialog-actions">
                      <button
                        className="secondary-button"
                        onClick={() => {
                          setReviewCategory(null);
                          setReview(null);
                        }}
                      >
                        Закрыть
                      </button>
                      {started &&
                        qualificationOpen &&
                        !reviewCategory.confirmed && (
                          <button
                            className="confirm-results-button"
                            onClick={() => {
                              const category = reviewCategory;
                              setReviewCategory(null);
                              setReview(null);
                              setPending({ type: "confirm", category });
                            }}
                          >
                            <Check size={15} />
                            Подтвердить результаты
                          </button>
                        )}
                    </div>
                  </>
                )}
              </section>
            </div>
          )}
          {pending && (
            <ConfirmDialog
              title={pendingCopy.title}
              description={pendingCopy.description}
              confirmLabel={pendingCopy.label}
              danger={pendingCopy.danger}
              busy={busy}
              onCancel={() => setPending(null)}
              onConfirm={() => void applyAction()}
            />
          )}
        </div>
      </div>
    </section>
  );
}
