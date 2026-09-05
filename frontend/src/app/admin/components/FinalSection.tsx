"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Check,
  CheckCircle2,
  CircleAlert,
  Download,
  Eye,
  Flag,
  LayoutDashboard,
  LockKeyhole,
  Pencil,
  RotateCcw,
  Route,
  Save,
  Trophy,
  X,
} from "lucide-react";
import {
  cancelFinalDevelopment,
  confirmAllFinalCategories,
  confirmFinalCategory,
  downloadProtocolXlsx,
  completeFestival,
  FinalCategoryResults,
  FinalSetup,
  FinalStatus,
  getFinalCategoryResults,
  getFinalSetup,
  getFinalStatus,
  reopenAllFinalCategories,
  reopenCompletedFestival,
  reopenFinalCategory,
  startFinal,
  updateFinalCategoryRoutes,
  updateFinalParticipantResults,
} from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";

type FinalCategory = FinalSetup["categories"][number];
type FinalStatusCategory = FinalStatus["categories"][number];
type FinalRoute = FinalSetup["routes"][number];
type FinalRow = FinalCategoryResults["results"][number];
type FinalView = "overview" | "preparation" | "results" | "exports";
type PendingAction =
  | { type: "start" }
  | { type: "cancel" }
  | { type: "complete" }
  | { type: "reopen-completed" }
  | { type: "confirm-final-all" }
  | { type: "reopen-final-all" }
  | { type: "confirm-final"; category: FinalStatusCategory }
  | { type: "reopen-final"; category: FinalStatusCategory }
  | { type: "routes"; category: FinalCategory; routeIds: string[] }
  | {
      type: "result";
      categoryId: string;
      row: FinalRow;
      attempts: Array<{
        route_id: string;
        zone_attempt: number | null;
        top_attempt: number | null;
      }>;
    };

const sameRoutes = (left: string[], right: string[]) =>
  left.length === right.length && left.every((item) => right.includes(item));
const numberOrNull = (value: string) => {
  const number = Number(value);
  return value.trim() && Number.isInteger(number) && number > 0 ? number : null;
};

export function FinalSection({
  token,
  canExport,
  onUpdated,
}: {
  token: string;
  canExport: boolean;
  onUpdated: () => Promise<void>;
}) {
  const [status, setStatus] = useState<FinalStatus | null>(null);
  const [setup, setSetup] = useState<FinalSetup | null>(null);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [routeDrafts, setRouteDrafts] = useState<Record<string, string[]>>({});
  const [editingRouteCategories, setEditingRouteCategories] = useState<
    Set<string>
  >(new Set());
  const [finalView, setFinalView] = useState<FinalView>("overview");
  const [finalCategoryResults, setFinalCategoryResults] = useState<
    Record<string, FinalCategoryResults>
  >({});
  const [finalResults, setFinalResults] = useState<FinalCategoryResults | null>(
    null,
  );
  const [finalEditor, setFinalEditor] = useState<FinalRow | null>(null);
  const [attemptDraft, setAttemptDraft] = useState<
    Record<string, { zone: string; top: string }>
  >({});
  const [downloadingId, setDownloadingId] = useState("");

  async function download(category: FinalStatusCategory) {
    setDownloadingId(category.id);
    try {
      await downloadProtocolXlsx(token, "final", category.id, category.name);
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
          : "Не удалось загрузить этап соревнования",
      );
    }
  }, [token]);

  useEffect(() => {
    void load();
    const interval = window.setInterval(() => void load(), 3000);
    return () => window.clearInterval(interval);
  }, [load]);
  useEffect(() => {
    if (
      !status ||
      status.stage === "preparation" ||
      status.stage === "qualification"
    ) {
      setSetup(null);
      setFinalView("overview");
      return;
    }
    void getFinalSetup(token)
      .then(setSetup)
      .catch((reason) =>
        setError(
          reason instanceof Error
            ? reason.message
            : "Не удалось загрузить настройку финала",
        ),
      );
  }, [status?.stage, token]);
  useEffect(() => {
    if (
      !setup ||
      status?.stage === "preparation" ||
      status?.stage === "qualification"
    ) {
      setFinalCategoryResults({});
      return;
    }
    let cancelled = false;
    const refresh = () =>
      void Promise.all(
        setup.categories.map(async (category) => {
          try {
            return [
              category.id,
              await getFinalCategoryResults(token, category.id),
            ] as const;
          } catch {
            return null;
          }
        }),
      ).then((items) => {
        if (cancelled) return;
        const results: Record<string, FinalCategoryResults> = {};
        for (const item of items) if (item) results[item[0]] = item[1];
        setFinalCategoryResults(results);
      });
    refresh();
    const interval = window.setInterval(refresh, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [setup, status?.stage, token]);
  useEffect(() => {
    if (!finalResults || finalEditor) return;
    const refresh = () =>
      void getFinalCategoryResults(token, finalResults.category_id)
        .then((result) => {
          setFinalResults(result);
          setFinalCategoryResults((rows) => ({
            ...rows,
            [result.category_id]: result,
          }));
        })
        .catch(() => undefined);
    const interval = window.setInterval(refresh, 3000);
    return () => window.clearInterval(interval);
  }, [finalResults?.category_id, finalEditor, token]);

  async function applyAction() {
    if (!pending || !status) return;
    setBusy(true);
    try {
      if (pending.type === "routes") {
        if (!setup) return;
        setSetup(
          await updateFinalCategoryRoutes(
            token,
            pending.category.id,
            pending.routeIds,
            setup.event_version,
          ),
        );
        setRouteDrafts((drafts) => ({
          ...drafts,
          [pending.category.id]: pending.routeIds,
        }));
        setEditingRouteCategories((categories) => {
          const next = new Set(categories);
          next.delete(pending.category.id);
          return next;
        });
      } else if (pending.type === "result") {
        const updatedResults = await updateFinalParticipantResults(
          token,
          pending.categoryId,
          pending.row.participant_id,
          pending.row.version,
          pending.attempts,
        );
        setFinalResults(updatedResults);
        setFinalCategoryResults((results) => ({
          ...results,
          [updatedResults.category_id]: updatedResults,
        }));
        setFinalEditor(null);
      } else if (pending.type === "confirm-final-all") {
        setStatus(await confirmAllFinalCategories(token, status.event_version));
        await onUpdated();
      } else if (pending.type === "reopen-final-all") {
        setStatus(await reopenAllFinalCategories(token, status.event_version));
        await onUpdated();
      } else if (pending.type === "confirm-final") {
        setStatus(
          await confirmFinalCategory(token, pending.category.id, status.event_version),
        );
        await onUpdated();
      } else if (pending.type === "reopen-final") {
        setStatus(
          await reopenFinalCategory(token, pending.category.id, status.event_version),
        );
        await onUpdated();
      } else {
        const next =
          pending.type === "start"
            ? await startFinal(token, status.event_version)
            : pending.type === "cancel"
              ? await cancelFinalDevelopment(token, status.event_version)
              : pending.type === "reopen-completed"
                ? await reopenCompletedFestival(token, status.event_version)
                : await completeFestival(token, status.event_version);
        setStatus(next);
        await onUpdated();
      }
      setError("");
      setPending(null);
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

  async function openFinalResults(category: FinalCategory) {
    setFinalResults(null);
    setFinalEditor(null);
    setError("");
    try {
      setFinalResults(await getFinalCategoryResults(token, category.id));
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "Не удалось загрузить таблицу финала",
      );
    }
  }
  function startResultEdit(row: FinalRow) {
    setFinalEditor(row);
    setAttemptDraft(
      Object.fromEntries(
        row.attempts.map((item) => [
          item.route_id,
          {
            zone: item.zone_attempt?.toString() ?? "",
            top: item.top_attempt?.toString() ?? "",
          },
        ]),
      ),
    );
  }
  if (!status)
    return (
      <section className="final-pane">
        <div className="final-loading">Загрузка состояния квалификации…</div>
        {error && <div className="error-banner">{error}</div>}
      </section>
    );
  const confirmedCount = status.categories.filter(
    (item) => item.confirmed,
  ).length;
  const finalCategories = status.categories.filter(
    (item) => item.participates_in_final,
  );
  const finalConfirmedCount = finalCategories.filter(
    (item) => item.final_confirmed,
  ).length;
  const beforeFinal =
    status.stage === "preparation" || status.stage === "qualification";
  const groupsWithoutQualificationResults = status.categories
    .filter((item) => item.result_count === 0)
    .map((item) => item.name);
  const groupsWithoutFinalResults = status.categories
    .filter(
      (item) => item.participates_in_final && item.final_result_count === 0,
    )
    .map((item) => item.name);
  const qualificationWarning = groupsWithoutQualificationResults.length
    ? `По возрастным группам «${groupsWithoutQualificationResults.join("», «")}» ещё нет результатов квалификации. Вы уверены?`
    : "";
  const finalWarning = groupsWithoutFinalResults.length
    ? `По возрастным группам «${groupsWithoutFinalResults.join("», «")}» ещё нет результатов финала. Вы уверены?`
    : "";
  const podiums =
    setup?.categories
      .filter((category) => category.participates)
      .map((category) => ({
        category,
        rows: (finalCategoryResults[category.id]?.results ?? []).filter(
          (row) => row.place !== null && row.place <= 3 && row.score > 0,
        ),
      }))
      .filter((item) => item.rows.length > 0) ?? [];
  const actionCopy =
    pending?.type === "start"
      ? {
          title: "Запустить финал?",
          description:
            qualificationWarning ||
            "Проверьте квалификацию. Перед переходом система создаст резервную копию и зафиксирует результаты, финалистов и порядок выхода.",
          label: "Запустить финал",
          danger: true,
        }
      : pending?.type === "cancel"
        ? {
            title: "Вернуться к квалификации?",
            description:
              "Сначала будет сохранена копия текущего финала, затем база вернётся к состоянию перед его запуском.",
            label: "Отменить финал",
            danger: true,
          }
        : pending?.type === "complete"
          ? {
              title: "Завершить финал?",
              description:
                finalWarning ||
                "Перед завершением система создаст проверенную резервную копию с финальными результатами.",
              label: "Завершить финал",
              danger: true,
            }
          : pending?.type === "confirm-final-all"
            ? {
                title: "Подтвердить все результаты финала?",
                description:
                  finalWarning ||
                  "Результаты всех возрастных групп будут отмечены как проверенные.",
                label: "Подтвердить все группы",
                danger: Boolean(finalWarning),
              }
            : pending?.type === "reopen-final-all"
              ? {
                  title: "Снять подтверждение результатов финала?",
                  description:
                    "Подтверждение будет снято со всех возрастных групп. Результаты сохранятся.",
                  label: "Снять подтверждение",
                  danger: true,
                }
              : pending?.type === "confirm-final"
                ? {
                    title: `Подтвердить «${pending.category.name}»?`,
                    description:
                      pending.category.final_result_count === 0
                        ? `По возрастной группе «${pending.category.name}» ещё нет результатов финала. Вы уверены?`
                        : "Текущие финальные результаты будут отмечены как проверенные.",
                    label: "Подтвердить результаты",
                    danger: pending.category.final_result_count === 0,
                  }
                : pending?.type === "reopen-final"
                  ? {
                      title: `Снять подтверждение «${pending.category.name}»?`,
                      description:
                        "Группу потребуется проверить и подтвердить повторно перед завершением финала.",
                      label: "Снять подтверждение",
                      danger: false,
                    }
          : pending?.type === "reopen-completed"
            ? {
                title: "Отменить подтверждение финала?",
                description:
                  "Сначала будет сохранена копия текущего состояния, затем база вернётся к моменту перед подтверждением финальных результатов.",
                label: "Снять подтверждение",
                danger: true,
              }
            : pending?.type === "routes"
              ? {
                  title: `Сохранить трассы для «${pending.category.name}»?`,
                  description:
                    "Для категории будут назначены выбранные четыре финальные трассы.",
                  label: "Сохранить трассы",
                  danger: false,
                }
              : {
                  title: `Сохранить результат №${pending?.row.start_number}?`,
                  description:
                    "Финальные баллы и места категории будут пересчитаны. Изменение попадёт в журнал действий.",
                  label: "Сохранить результат",
                  danger: false,
                };

  return (
    <section className="final-workspace">
      <header className="admin-section-hero">
        <div>
          <div className="eyebrow">Этап соревнования</div>
          <h1>
            {beforeFinal
              ? "Финал"
              : status.stage === "final"
                ? "Финал запущен"
                : "Фестиваль завершён"}
          </h1>
          <p>
            {beforeFinal
              ? "Запуск станет доступен после проверки всех возрастных групп в разделе «Квалификация»."
              : status.stage === "final"
                ? "Назначьте трассы категориям и вносите финальные результаты."
                : "Итоговое состояние зафиксировано. При необходимости завершение можно отменить."}
          </p>
        </div>
        <div className={`section-health ${status.stage}`}>
          <Trophy size={22} />
          <span>
            <strong>
              {beforeFinal
                ? `${confirmedCount}/${status.categories.length}`
                : `${finalConfirmedCount}/${finalCategories.length}`}
            </strong>
            <small>групп подтверждено</small>
          </span>
        </div>
      </header>
      <div className="final-content-grid">
        <aside className="final-sidebar">
          <span className="eyebrow">Финал</span>
          <button
            className={finalView === "overview" ? "active" : ""}
            onClick={() => setFinalView("overview")}
          >
            <LayoutDashboard size={17} />
            Главное
          </button>
          <button
            disabled={beforeFinal}
            className={finalView === "preparation" ? "active" : ""}
            onClick={() => setFinalView("preparation")}
          >
            <Route size={17} />
            Подготовка
          </button>
          <button
            disabled={beforeFinal}
            className={finalView === "results" ? "active" : ""}
            onClick={() => setFinalView("results")}
          >
            <Trophy size={17} />
            Результаты
          </button>
          <button
            className={finalView === "exports" ? "active" : ""}
            onClick={() => setFinalView("exports")}
          >
            <Download size={17} />
            Выгрузка
          </button>
        </aside>
        <div className="final-pane">
          {error && <div className="error-banner compact">{error}</div>}
          {beforeFinal && finalView === "overview" && (
            <div className="final-start-card final-launch-card">
              <span>
                <LockKeyhole size={23} />
                <span>
                  <strong>
                    {status.all_categories_confirmed
                      ? "Квалификация подтверждена"
                      : "Сначала проверьте квалификацию"}
                  </strong>
                  <small>
                    {status.all_categories_confirmed
                      ? "Все возрастные группы проверены. Перед запуском будет создана резервная копия."
                      : "Перейдите в раздел «Квалификация» и подтвердите результаты всех возрастных групп."}
                  </small>
                </span>
              </span>
              <button
                className="primary-action"
                disabled={
                  !status.all_categories_confirmed ||
                  !status.qualification_started_at
                }
                title={
                  !status.qualification_started_at
                    ? "Сначала начните квалификацию"
                    : !status.all_categories_confirmed
                      ? "Подтвердите результаты в разделе «Квалификация»"
                      : "Запустить финал"
                }
                onClick={() => setPending({ type: "start" })}
              >
                <Flag size={17} />
                Запустить финал
              </button>
            </div>
          )}
          {!beforeFinal && finalView === "overview" && (
            <>
              <div className="final-snapshot-card">
                <div>
                  <span>
                    <strong>{status.snapshot_results}</strong>
                    <small>результатов зафиксировано</small>
                  </span>
                  <span>
                    <strong>{status.snapshot_finalists}</strong>
                    <small>финалистов</small>
                  </span>
                  <span>
                    <strong>{status.categories.length}</strong>
                    <small>категорий</small>
                  </span>
                </div>
                <div className="final-stage-actions">
                  {status.stage === "final" ? (
                    <>
                      <button
                        className="danger-outline-button"
                        onClick={() => setPending({ type: "cancel" })}
                      >
                        <RotateCcw size={16} />
                        Отменить финал
                      </button>
                      <button
                        className="primary-action"
                        disabled={!status.all_final_categories_confirmed}
                        title={
                          status.all_final_categories_confirmed
                            ? "Завершить финал"
                            : "Сначала подтвердите результаты всех возрастных групп"
                        }
                        onClick={() => setPending({ type: "complete" })}
                      >
                        <CheckCircle2 size={16} />
                        Завершить финал
                      </button>
                    </>
                  ) : (
                    <button
                      className="danger-outline-button"
                      onClick={() => setPending({ type: "reopen-completed" })}
                    >
                      <RotateCcw size={16} />
                      Отменить подтверждение финала
                    </button>
                  )}
                </div>
              </div>
              <section className="final-podiums">
                <div className="final-panel-heading">
                  <div>
                    <span className="eyebrow">Итоги финала</span>
                    <h2>Победители и призёры</h2>
                  </div>
                  <Trophy size={22} />
                </div>
                {podiums.length ? (
                  <div className="final-podium-grid">
                    {podiums.map(({ category, rows }) => (
                      <article key={category.id}>
                        <div>
                          <span>{category.short_name}</span>
                          <strong>{category.name}</strong>
                        </div>
                        {rows.map((row) => (
                          <p
                            key={row.id}
                            className={`final-medal place-${row.place}`}
                          >
                            <b>
                              {row.place === 1
                                ? "1"
                                : row.place === 2
                                  ? "2"
                                  : "3"}
                            </b>
                            <span>
                              {row.full_name}
                              <small>
                                №{row.start_number} · {row.club}
                              </small>
                            </span>
                          </p>
                        ))}
                      </article>
                    ))}
                  </div>
                ) : (
                  <div className="final-podium-empty">
                    Призёры появятся здесь после внесения результатов финала.
                  </div>
                )}
              </section>
            </>
          )}
          {!beforeFinal && finalView === "preparation" && (
            <FinalPreparationPanel
              setup={setup}
              stage={status.stage}
              routeDrafts={routeDrafts}
              editingCategories={editingRouteCategories}
              onRoutesChange={setRouteDrafts}
              onEdit={(categoryId) =>
                setEditingRouteCategories((categories) =>
                  new Set(categories).add(categoryId),
                )
              }
              onCancelEdit={(category) => {
                setRouteDrafts((drafts) => ({
                  ...drafts,
                  [category.id]: category.route_ids,
                }));
                setEditingRouteCategories((categories) => {
                  const next = new Set(categories);
                  next.delete(category.id);
                  return next;
                });
              }}
              onSave={(category, routeIds) =>
                setPending({ type: "routes", category, routeIds })
              }
            />
          )}
          {!beforeFinal && finalView === "results" && (
            <FinalResultsPanel
              setup={setup}
              status={status}
              onOpenResults={openFinalResults}
              onConfirm={(category) =>
                setPending({ type: "confirm-final", category })
              }
              onReopen={(category) =>
                setPending({ type: "reopen-final", category })
              }
              onConfirmAll={() => setPending({ type: "confirm-final-all" })}
              onReopenAll={() => setPending({ type: "reopen-final-all" })}
            />
          )}
          {finalView === "exports" && (
            <section className="final-exports">
              <div className="final-panel-heading">
                <div>
                  <span className="eyebrow">Протоколы финала</span>
                  <h2>Выгрузка по возрастным группам</h2>
                  <p>
                    Файл формируется по подтверждённым итогам финала.
                  </p>
                </div>
                <Download size={22} />
              </div>
              <div>
                {status.categories
                  .filter((category) => category.participates_in_final)
                  .map((category) => (
                    <button
                      key={category.id}
                      disabled={!canExport || !category.final_confirmed || Boolean(downloadingId)}
                      title={
                        !canExport
                          ? "Недостаточно прав на формирование выгрузок"
                          : !category.final_confirmed
                            ? "Сначала подтвердите результаты финала"
                            : "Скачать итоговый протокол результатов"
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
          {finalResults && (
            <FinalResultsDialog
              results={finalResults}
              editor={finalEditor}
              attemptDraft={attemptDraft}
              stage={status.stage}
              confirmed={Boolean(
                status.categories.find(
                  (category) => category.id === finalResults.category_id,
                )?.final_confirmed,
              )}
              onClose={() => {
                setFinalResults(null);
                setFinalEditor(null);
              }}
              onEdit={startResultEdit}
              onDraft={setAttemptDraft}
              onSave={(row, attempts) =>
                setPending({
                  type: "result",
                  categoryId: finalResults.category_id,
                  row,
                  attempts,
                })
              }
              onCancelEdit={() => setFinalEditor(null)}
              onConfirm={() => {
                const category = status.categories.find(
                  (item) => item.id === finalResults.category_id,
                );
                if (!category) return;
                setFinalResults(null);
                setFinalEditor(null);
                setPending({ type: "confirm-final", category });
              }}
              onReopen={() => {
                const category = status.categories.find(
                  (item) => item.id === finalResults.category_id,
                );
                if (!category) return;
                setFinalResults(null);
                setFinalEditor(null);
                setPending({ type: "reopen-final", category });
              }}
            />
          )}
          {pending && (
            <ConfirmDialog
              title={actionCopy.title}
              description={actionCopy.description}
              confirmLabel={actionCopy.label}
              danger={actionCopy.danger}
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

function FinalPreparationPanel({
  setup,
  stage,
  routeDrafts,
  editingCategories,
  onRoutesChange,
  onEdit,
  onCancelEdit,
  onSave,
}: {
  setup: FinalSetup | null;
  stage: string;
  routeDrafts: Record<string, string[]>;
  editingCategories: Set<string>;
  onRoutesChange: (value: Record<string, string[]>) => void;
  onEdit: (categoryId: string) => void;
  onCancelEdit: (category: FinalCategory) => void;
  onSave: (category: FinalCategory, routeIds: string[]) => void;
}) {
  if (!setup)
    return (
      <div className="final-loading">Загружаем настройку финальных трасс…</div>
    );
  const finalRoutes = setup.routes;
  function changeSelection(
    category: FinalCategory,
    selected: string[],
    route: FinalRoute,
  ) {
    const blockStart =
      route.number === 1 || route.number === 5 ? route.number : null;
    const routeIds =
      blockStart === null
        ? selected.includes(route.id)
          ? selected.filter((id) => id !== route.id)
          : selected.length < 4
            ? [...selected, route.id]
            : selected
        : finalRoutes
            .filter(
              (item) =>
                item.number >= blockStart && item.number < blockStart + 4,
            )
            .map((item) => item.id);
    onRoutesChange({ ...routeDrafts, [category.id]: routeIds });
  }
  return (
    <section className="final-setup">
      <div className="final-setup-head">
        <div>
          <span className="eyebrow">Подготовка финала</span>
          <h2>Трассы и возрастные группы</h2>
          <p>
            Здесь показаны только категории с положительным количеством
            финалистов. Назначьте каждой ровно четыре трассы.
          </p>
        </div>
      </div>
      <div className="final-route-overview">
        {setup.routes.map((route) => (
          <article key={route.id}>
            <strong>{route.name}</strong>
            <small>
              {route.assigned_categories.length
                ? route.assigned_categories.join(" · ")
                : "Не назначена"}
            </small>
          </article>
        ))}
      </div>
      <div className="final-category-setup-list">
        {setup.categories.map((category) => {
          const selected = routeDrafts[category.id] ?? category.route_ids;
          const configured = selected.length === 4;
          const editing = editingCategories.has(category.id);
          return (
            <article key={category.id} className="final-category-setup">
              <div className="final-category-title">
                <span>{category.short_name}</span>
                <div>
                  <strong>{category.name}</strong>
                  <small>{category.finalist_count} финалистов</small>
                </div>
              </div>
              <div className="final-route-choice">
                {setup.routes.map((route) => (
                  <button
                    key={route.id}
                    title={
                      route.number === 1
                        ? "Выбрать трассы 1–4"
                        : route.number === 5
                          ? "Выбрать трассы 5–8"
                          : undefined
                    }
                    disabled={stage !== "final" || (configured && !editing)}
                    className={selected.includes(route.id) ? "active" : ""}
                    onClick={() => changeSelection(category, selected, route)}
                  >
                    {route.number}
                  </button>
                ))}
              </div>
              <div className="final-category-actions">
                <small className={configured ? "ready" : ""}>
                  {configured
                    ? "Назначены 4 трассы"
                    : `Выбрано ${selected.length}/4`}
                </small>
                {stage === "final" && configured && !editing && (
                  <button
                    className="secondary-button compact-action"
                    onClick={() => onEdit(category.id)}
                  >
                    <Pencil size={14} />
                    Изменить
                  </button>
                )}
                {stage === "final" && editing && (
                  <button
                    className="secondary-button compact-action"
                    onClick={() => onCancelEdit(category)}
                  >
                    <X size={14} />
                    Отмена
                  </button>
                )}
                {stage === "final" &&
                  !sameRoutes(selected, category.route_ids) && (
                    <button
                      className="secondary-button compact-action"
                      disabled={!configured}
                      onClick={() => onSave(category, selected)}
                    >
                      <Save size={14} />
                      Сохранить
                    </button>
                  )}
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}

function FinalResultsPanel({
  setup,
  status,
  onOpenResults,
  onConfirm,
  onReopen,
  onConfirmAll,
  onReopenAll,
}: {
  setup: FinalSetup | null;
  status: FinalStatus;
  onOpenResults: (category: FinalCategory) => void;
  onConfirm: (category: FinalStatusCategory) => void;
  onReopen: (category: FinalStatusCategory) => void;
  onConfirmAll: () => void;
  onReopenAll: () => void;
}) {
  if (!setup)
    return <div className="final-loading">Загружаем возрастные группы…</div>;
  const setupById = new Map(setup.categories.map((category) => [category.id, category]));
  const categories = status.categories.filter((category) => category.participates_in_final);
  const confirmedCount = categories.filter((category) => category.final_confirmed).length;
  const allConfigured = categories.every(
    (category) => setupById.get(category.id)?.route_ids.length === 4,
  );
  return (
    <>
      <div className="final-progress">
        <span>
          <strong>{confirmedCount}/{categories.length}</strong>
          <small>возрастных групп подтверждено</small>
        </span>
        <div>
          <i
            style={{
              width: `${categories.length ? (confirmedCount / categories.length) * 100 : 0}%`,
            }}
          />
        </div>
        {status.stage === "final" && (
          <span className="qualification-progress-actions">
            {confirmedCount > 0 && (
              <button
                className="secondary-button confirm-all-button"
                onClick={onReopenAll}
              >
                <RotateCcw size={16} />
                Снять подтверждение
              </button>
            )}
            <button
              className="secondary-button confirm-all-button"
              disabled={status.all_final_categories_confirmed || !allConfigured}
              title={!allConfigured ? "Сначала назначьте по четыре трассы всем группам" : undefined}
              onClick={onConfirmAll}
            >
              <CheckCircle2 size={16} />
              {status.all_final_categories_confirmed
                ? "Всё подтверждено"
                : "Подтвердить финал"}
            </button>
          </span>
        )}
      </div>
      <div className="qualification-category-list">
        {categories.map((category) => {
          const categorySetup = setupById.get(category.id);
          const configured = categorySetup?.route_ids.length === 4;
          return (
            <article
              key={category.id}
              className={
                category.final_confirmed
                  ? "qualification-category confirmed"
                  : "qualification-category"
              }
            >
              <span className="qualification-status-icon">
                {category.final_confirmed ? (
                  <CheckCircle2 size={21} />
                ) : (
                  <CircleAlert size={21} />
                )}
              </span>
              <div>
                <strong>{category.name}</strong>
                <small>
                  {category.final_result_count} результатов · {category.finalist_count} финалистов
                </small>
              </div>
              <span className="qualification-category-actions">
                <button
                  className="secondary-button compact-action"
                  disabled={!configured}
                  title={configured ? "Открыть таблицу финала" : "Сначала назначьте четыре трассы в разделе «Подготовка»"}
                  onClick={() => categorySetup && onOpenResults(categorySetup)}
                >
                  <Eye size={14} />
                  Просмотреть
                </button>
                {status.stage === "final" && (
                  category.final_confirmed ? (
                    <button
                      className="secondary-button compact-action"
                      onClick={() => onReopen(category)}
                    >
                      <RotateCcw size={14} />
                      Снять
                    </button>
                  ) : (
                    <button
                      className="confirm-results-button"
                      disabled={!configured}
                      title={!configured ? "Сначала назначьте четыре трассы в разделе «Подготовка»" : undefined}
                      onClick={() => onConfirm(category)}
                    >
                      <Check size={15} />
                      Подтвердить
                    </button>
                  )
                )}
              </span>
            </article>
          );
        })}
      </div>
    </>
  );
}

function FinalResultsDialog({
  results,
  editor,
  attemptDraft,
  stage,
  confirmed,
  onClose,
  onEdit,
  onDraft,
  onSave,
  onCancelEdit,
  onConfirm,
  onReopen,
}: {
  results: FinalCategoryResults;
  editor: FinalRow | null;
  attemptDraft: Record<string, { zone: string; top: string }>;
  stage: string;
  confirmed: boolean;
  onClose: () => void;
  onEdit: (row: FinalRow) => void;
  onDraft: (draft: Record<string, { zone: string; top: string }>) => void;
  onSave: (
    row: FinalRow,
    attempts: Array<{
      route_id: string;
      zone_attempt: number | null;
      top_attempt: number | null;
    }>,
  ) => void;
  onCancelEdit: () => void;
  onConfirm: () => void;
  onReopen: () => void;
}) {
  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="final-results-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="final-results-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <button className="dialog-close" onClick={onClose} title="Закрыть">
          <X size={18} />
        </button>
        <div className="dialog-icon">
          <Trophy size={22} />
        </div>
        <div className="eyebrow">Общая таблица финала</div>
        <h2 id="final-results-title">{results.category_name}</h2>
        <div className="final-results-table-wrap">
          <table className="final-results-table">
            <thead>
              <tr>
                <th>Место</th>
                <th>№</th>
                <th>Участник</th>
                <th>Квал.</th>
                <th>Выход</th>
                {results.routes.map((route) => (
                  <th key={route.id}>{route.name}</th>
                ))}
                <th>Топы</th>
                <th>Зоны</th>
                <th>Баллы</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {results.results.map((row) => (
                <tr key={row.id}>
                  <td>
                    <strong>{row.place ?? "—"}</strong>
                  </td>
                  <td>{row.start_number}</td>
                  <td>
                    {row.full_name}
                    <small>{row.club}</small>
                  </td>
                  <td>{row.qualification_place}</td>
                  <td>{row.exit_order ?? "—"}</td>
                  {row.attempts.map((attempt) => (
                    <td key={attempt.route_id}>
                      {attempt.top_attempt ? (
                        <>
                          <strong className="attempt-kind">Т</strong>{" "}
                          {attempt.top_attempt}
                        </>
                      ) : attempt.zone_attempt ? (
                        <>
                          <strong className="attempt-kind">З</strong>{" "}
                          {attempt.zone_attempt}
                        </>
                      ) : (
                        "—"
                      )}
                      <small>{attempt.score}</small>
                    </td>
                  ))}
                  <td>
                    {row.top_count} / {row.top_attempts || "—"}
                  </td>
                  <td>
                    {row.zone_count} / {row.zone_attempts || "—"}
                  </td>
                  <td>
                    <strong>{row.score}</strong>
                  </td>
                  <td>
                    {stage === "final" && (
                      <button
                        className="icon-button"
                        title="Изменить результат"
                        onClick={() => onEdit(row)}
                      >
                        <Pencil size={15} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {results.results.length === 0 && (
            <div className="qualification-review-empty">
              В этой категории нет финалистов.
            </div>
          )}
        </div>
        {editor && (
          <div className="final-result-editor">
            <div>
              <strong>
                Результат №{editor.start_number} · {editor.full_name}
              </strong>
              <small>
                Укажите попытку зоны и топа. Если есть топ, в баллах учитывается
                только его попытка.
              </small>
            </div>
            <div className="final-attempt-fields">
              {editor.attempts.map((attempt) => (
                <label key={attempt.route_id}>
                  <strong>{attempt.route_name}</strong>
                  <span>
                    Зона
                    <input
                      type="number"
                      min="1"
                      value={attemptDraft[attempt.route_id]?.zone ?? ""}
                      onChange={(event) =>
                        onDraft({
                          ...attemptDraft,
                          [attempt.route_id]: {
                            ...attemptDraft[attempt.route_id],
                            zone: event.target.value,
                          },
                        })
                      }
                    />
                  </span>
                  <span>
                    Топ
                    <input
                      type="number"
                      min="1"
                      value={attemptDraft[attempt.route_id]?.top ?? ""}
                      onChange={(event) =>
                        onDraft({
                          ...attemptDraft,
                          [attempt.route_id]: {
                            ...attemptDraft[attempt.route_id],
                            top: event.target.value,
                          },
                        })
                      }
                    />
                  </span>
                </label>
              ))}
            </div>
            <div className="dialog-actions">
              <button className="secondary-button" onClick={onCancelEdit}>
                Отмена
              </button>
              <button
                className="confirm-results-button"
                onClick={() =>
                  onSave(
                    editor,
                    editor.attempts.map((attempt) => ({
                      route_id: attempt.route_id,
                      zone_attempt: numberOrNull(
                        attemptDraft[attempt.route_id]?.zone ?? "",
                      ),
                      top_attempt: numberOrNull(
                        attemptDraft[attempt.route_id]?.top ?? "",
                      ),
                    })),
                  )
                }
              >
                <Save size={15} />
                Проверить и сохранить
              </button>
            </div>
          </div>
        )}
        <div className="dialog-actions">
          <button className="secondary-button" onClick={onClose}>
            Закрыть
          </button>
          {stage === "final" && !editor && (
            confirmed ? (
              <button className="secondary-button" onClick={onReopen}>
                <RotateCcw size={15} />
                Снять подтверждение
              </button>
            ) : (
              <button className="confirm-results-button" onClick={onConfirm}>
                <Check size={15} />
                Подтвердить результаты
              </button>
            )
          )}
        </div>
      </section>
    </div>
  );
}
