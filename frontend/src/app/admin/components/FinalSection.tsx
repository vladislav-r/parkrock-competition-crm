"use client";

import { finalRouteName } from "@/lib/final-route-display";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Check,
  CheckCircle2,
  Users,
  Download,
  Eye,
  Flag,
  Pencil,
  RotateCcw,
  Route,
  Save,
  Trophy,
  X,
} from "lucide-react";
import {
  cancelFinalDevelopment,
  clearAdminReadFailures,
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
  updateFinalCategoryParticipation,
  updateFinalParticipantResults,
} from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";
import { FinalStreamsPanel } from "./FinalStreamsPanel";
import { JudgeConflictsPanel } from "./JudgeConflictsPanel";

type FinalCategory = FinalSetup["categories"][number];
type FinalStatusCategory = FinalStatus["categories"][number];
type FinalRow = FinalCategoryResults["results"][number];
type FinalView = "preparation" | "results" | "exports";
type PendingAction =
  | { type: "start" }
  | { type: "cancel" }
  | { type: "complete" }
  | { type: "reopen-completed" }
  | { type: "confirm-final-all" }
  | { type: "reopen-final-all" }
  | { type: "confirm-final"; category: FinalStatusCategory }
  | { type: "reopen-final"; category: FinalStatusCategory }
  | { type: "participation"; category: FinalCategory; participates: boolean }
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

const numberOrNull = (value: string) => {
  const number = Number(value);
  return value.trim() && Number.isInteger(number) && number > 0 ? number : null;
};

export function FinalSection({
  token,
  canExport,
  canResolveConflicts,
  onUpdated,
}: {
  token: string;
  canExport: boolean;
  canResolveConflicts: boolean;
  onUpdated: () => Promise<void>;
}) {
  const [status, setStatus] = useState<FinalStatus | null>(null);
  const [setup, setSetup] = useState<FinalSetup | null>(null);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [finalView, setFinalView] = useState<FinalView>("preparation");
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
  const statusRequest = useRef<AbortController | null>(null);
  const finalReads = useRef<AbortController | null>(null);
  const changingStage = useRef(false);
  const load = useCallback(async () => {
    if (changingStage.current) return;
    statusRequest.current?.abort();
    const controller = new AbortController();
    statusRequest.current = controller;
    try {
      const next = await getFinalStatus(token, controller.signal);
      if (controller.signal.aborted) return;
      setStatus(next);
      setError("");
    } catch (reason) {
      if (controller.signal.aborted) return;
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
    return () => { window.clearInterval(interval); statusRequest.current?.abort(); };
  }, [load]);
  useEffect(() => {
    const controller = new AbortController();
    finalReads.current = controller;
    if (!status || status.stage === "preparation" || status.stage === "qualification") {
      setSetup(null);
      setFinalResults(null);
      setFinalEditor(null);
      setFinalView("preparation");
      if (status) clearAdminReadFailures("/api/v1/admin/final/");
      return () => controller.abort();
    }
    if (busy) return () => controller.abort();
    const refreshSetup = () => void getFinalSetup(token, controller.signal)
      .then(value => { if (!controller.signal.aborted) setSetup(previous => !previous || value.event_version >= previous.event_version ? value : previous); })
      .catch(reason => { if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Не удалось загрузить настройку финала"); });
    refreshSetup();
    const interval = window.setInterval(refreshSetup, 3000);
    return () => { controller.abort(); window.clearInterval(interval); };
  }, [status?.stage, status?.event_version, token, busy]);
  const openCategory = setup?.categories.find(item => item.id === finalResults?.category_id);
  useEffect(() => {
    if (!finalResults) return;
    if (!openCategory?.participates || openCategory.route_ids.length !== 4) {
      setFinalResults(null); setFinalEditor(null);
      return;
    }
    if (finalEditor || busy || !["final", "completed"].includes(status?.stage ?? "")) return;
    const controller = new AbortController();
    const refresh = () =>
      void getFinalCategoryResults(token, finalResults.category_id, controller.signal)
        .then((result) => {
          if (controller.signal.aborted) return;
          setFinalResults(result);

        })
        .catch(() => undefined);
    const interval = window.setInterval(refresh, 3000);
    return () => { controller.abort(); window.clearInterval(interval); };
  }, [finalResults?.category_id, finalEditor, openCategory?.participates, openCategory?.route_ids.length, token, status?.stage, busy]);

  async function applyAction() {
    if (!pending || !status) return;
    const stageAction = ["start", "cancel", "complete", "reopen-completed"].includes(pending.type);
    if (stageAction) {
      changingStage.current = true;
      statusRequest.current?.abort();
      finalReads.current?.abort();
    }
    setBusy(true);
    try {
      if (pending.type === "participation") {
        if (!setup) return;
        setSetup(await updateFinalCategoryParticipation(token, pending.category.id, pending.participates, setup.event_version));
        await load();
        await onUpdated();
      } else if (pending.type === "result") {
        const updatedResults = await updateFinalParticipantResults(
          token,
          pending.categoryId,
          pending.row.participant_id,
          pending.row.version,
          pending.attempts,
        );
        setFinalResults(updatedResults);

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
      changingStage.current = false;
      await load();
    } finally {
      changingStage.current = false;
      setBusy(false);
    }
  }

  useEffect(() => {
    if (setup && finalResults && !setup.categories.some((category) => category.id === finalResults.category_id && category.participates)) {
      setFinalResults(null);
      setFinalEditor(null);
    }
  }, [setup, finalResults]);

  async function openFinalResults(category: FinalCategory) {
    setFinalResults(null);
    setFinalEditor(null);
    setError("");
    const signal = finalReads.current?.signal;
    try {
      const result = await getFinalCategoryResults(token, category.id, signal);
      if (!signal?.aborted) setFinalResults(result);
    } catch (reason) {
      if (signal?.aborted) return;
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
            : pending?.type === "participation"
              ? {
                  title: `${pending.participates ? "Включить" : "Выключить"} финал для «${pending.category.name}»?`,
                  description: pending.participates
                    ? "Группа 7–9 лет будет участвовать в финале: для неё потребуются четыре трассы, будут считаться результаты и места. Финал станет доступен в админке, судействе и публичных результатах."
                    : "Группа будет исключена из финала, его расчётов и всех финальных таблиц. Сохранённые назначения и результаты не удаляются и вернутся при повторном включении.",
                  label: pending.participates ? "Включить финал" : "Выключить финал",
                  danger: true,
                }
              : {
                  title: `Сохранить результат №${pending?.row.start_number}?`,
                  description:
                    "Финальные баллы и места категории будут пересчитаны. Изменение попадёт в журнал действий.",
                  label: "Сохранить результат",
                  danger: false,
                };

  return (
    <section className="final-workspace stage-relief">
      <header className="admin-section-hero">
        <div>

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
      <JudgeConflictsPanel token={token} canResolve={canResolveConflicts} onUpdated={async () => { await load(); await onUpdated(); }} />
      <div className="final-stage-actions final-lifecycle-actions">
        {beforeFinal ? (
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
        ) : status.stage === "final" ? (
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
      <div className="final-content-grid">
        <aside className="final-sidebar">
          <span className="eyebrow">Финал</span>
          <button data-view-action
            disabled={beforeFinal}
            className={finalView === "preparation" ? "active" : ""}
            onClick={() => setFinalView("preparation")}
          >
            <Route size={17} />
            Распределение
          </button>
          <button data-view-action
            disabled={beforeFinal}
            className={finalView === "results" ? "active" : ""}
            onClick={() => setFinalView("results")}
          >
            <Trophy size={17} />
            Результаты
          </button>
          <button data-view-action
            className={finalView === "exports" ? "active" : ""}
            onClick={() => setFinalView("exports")}
          >
            <Download size={17} />
            Выгрузка
          </button>
        </aside>
        <div className="final-pane">
          {error && <div className="error-banner compact">{error}</div>}
          {!beforeFinal && finalView === "preparation" && (
            <FinalStreamsPanel
              token={token} setup={setup} stage={status.stage}
              onUpdated={(value) => { setSetup(value); void load(); }}
              onParticipationChange={(category, participates) => setPending({type: "participation", category, participates})}
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
                  <Users size={21} />
                )}
              </span>
              <div>
                <strong>{category.name}</strong>
                <small>
                  {category.final_result_count} результатов · {category.finalist_count} финалистов
                </small>
              </div>
              <span className="qualification-category-actions">
                <span className={`stage-category-status${category.final_confirmed ? " confirmed" : ""}`}>{category.final_confirmed ? "Подтверждено" : !configured ? "Нет трасс" : category.final_result_count ? "Ожидает проверки" : "Нет результатов"}</span>
                <button data-view-action
                  className="secondary-button compact-action"
                  disabled={!configured}
                  title={configured ? "Открыть таблицу финала" : "Сначала назначьте четыре трассы в разделе «Распределение»"}
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
                      title={!configured ? "Сначала назначьте четыре трассы в разделе «Распределение»" : undefined}
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
        <button data-view-action className="dialog-close" onClick={onClose} title="Закрыть">
          <X size={18} />
        </button>
        <header className="stage-review-head"><h2 id="final-results-title">{results.category_name}</h2></header>
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
                  <th key={route.id}>{finalRouteName(route.number, route.name)}</th>
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
                  <td><span className="stage-result-number">{row.start_number}</span></td>
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
                  <strong>{finalRouteName(attempt.route_number, attempt.route_name)}</strong>
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
          <button data-view-action className="secondary-button" onClick={onClose}>
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
