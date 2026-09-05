"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ArchiveRestore,
  EyeOff,
  Flag,
  Layers3,
  RotateCcw,
  ShieldAlert,
  Tags,
  Trash2,
  UserCheck,
  Users,
  Waypoints,
} from "lucide-react";
import {
  CompetitionResetStatus,
  CompetitionResetTarget,
  getCompetitionResetStatus,
  resetCompetitionData,
} from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";
import { RouteToast, type RouteNotification } from "./RoutesSection";

type ResetItem = {
  target: CompetitionResetTarget;
  title: string;
  description: string;
  consequence: string;
  icon: typeof Trash2;
  countKey?: keyof CompetitionResetStatus["counts"];
  factory?: boolean;
};

const ITEMS: ResetItem[] = [
  {
    target: "stage",
    title: "Этап соревнования",
    description: "Вернуть фестиваль в подготовку.",
    consequence:
      "Результаты обеих стадий и подтверждения будут очищены; заявки, участники и настройки сохранятся.",
    icon: Flag,
  },
  {
    target: "qualification_results",
    title: "Результаты квалификации",
    description: "Очистить отметки по трассам и подтверждения групп.",
    consequence:
      "Финальные результаты и настройки, зависящие от квалификации, также будут очищены.",
    icon: Waypoints,
    countKey: "qualification_results",
  },
  {
    target: "final_results",
    title: "Результаты финала",
    description: "Очистить попытки финалистов.",
    consequence:
      "Назначение трасс по группам сохранится. Завершённый фестиваль вернётся в финал.",
    icon: ArchiveRestore,
    countKey: "final_results",
  },
  {
    target: "final_setup",
    title: "Настройки финала",
    description: "Очистить распределение финальных трасс по группам.",
    consequence: "Вместе с распределением будут очищены финальные результаты.",
    icon: Layers3,
    countKey: "final_setup",
  },
  {
    target: "applications",
    title: "Файлы заявок",
    description: "Удалить загруженные XLSX-заявки.",
    consequence: "Уже созданные из них участники сохранятся.",
    icon: Trash2,
    countKey: "applications",
  },
  {
    target: "participants",
    title: "Участники",
    description: "Удалить всех участников и их данные ресепшена.",
    consequence:
      "Результаты и этап соревнования будут сброшены; клубы и сеты сохранятся.",
    icon: Users,
    countKey: "participants",
  },
  {
    target: "reception",
    title: "Статусы ресепшена",
    description: "Снять отметки о прибытии, оплате и выдаче.",
    consequence: "Участники, их сеты и спортивные результаты сохранятся.",
    icon: UserCheck,
    countKey: "reception",
  },
  {
    target: "clubs",
    title: "Клубы",
    description: "Удалить справочник клубов.",
    consequence:
      "Сначала нужно отдельно сбросить участников, связанных с клубами.",
    icon: Tags,
    countKey: "clubs",
  },
  {
    target: "sets",
    title: "Сеты",
    description: "Удалить все сеты.",
    consequence:
      "Сначала нужно отдельно сбросить участников, распределённых по сетам.",
    icon: Layers3,
    countKey: "sets",
  },
  {
    target: "set_statuses",
    title: "Статусы сетов",
    description: "Вернуть все сеты в черновики.",
    consequence: "Состав сетов, участники и результаты сохранятся.",
    icon: Layers3,
    countKey: "set_statuses",
  },
  {
    target: "routes",
    title: "Трассы квалификации",
    description: "Удалить трассы и настроенную таблицу баллов.",
    consequence:
      "Квалификационные и финальные результаты будут очищены, этап вернётся в подготовку.",
    icon: Waypoints,
    countKey: "routes",
  },
  {
    target: "categories",
    title: "Категории",
    description: "Удалить возрастные группы и медальные диапазоны.",
    consequence:
      "Все результаты будут очищены, этап вернётся в подготовку. Участники сохранятся.",
    icon: Tags,
    countKey: "categories",
  },
  {
    target: "judge_assignments",
    title: "Назначения судей",
    description: "Снять закреплённые за судьями трассы.",
    consequence: "Учётные записи и роли сотрудников сохранятся.",
    icon: UserCheck,
    countKey: "judge_assignments",
  },
  {
    target: "publication",
    title: "Публичная детализация",
    description: "Закрыть детальные результаты по трассам.",
    consequence:
      "Публичные результаты останутся доступны, но окно участника будет закрыто.",
    icon: EyeOff,
    countKey: "publication",
  },
  {
    target: "all",
    title: "Заводское состояние",
    description: "Удалить все вручную заполненные данные соревнования.",
    consequence:
      "Сотрудники, права, журнал и резервные копии сохранятся. После сброса появится нулевой снимок.",
    icon: ShieldAlert,
    factory: true,
  },
];

export function CompetitionResetPanel({
  token,
  onChanged,
}: {
  token: string;
  onChanged: () => Promise<void>;
}) {
  const [status, setStatus] = useState<CompetitionResetStatus | null>(null);
  const [pending, setPending] = useState<ResetItem | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<RouteNotification | null>(null);
  const load = useCallback(async () => {
    try {
      setStatus(await getCompetitionResetStatus(token));
    } catch (error) {
      setNotice({
        type: "error",
        title:
          error instanceof Error
            ? error.message
            : "Не удалось загрузить состояние данных",
      });
    }
  }, [token]);
  useEffect(() => {
    void load();
  }, [load]);

  async function applyReset() {
    if (!pending) return;
    setBusy(true);
    try {
      const result = await resetCompetitionData(token, pending.target);
      setPending(null);
      await Promise.all([load(), onChanged()]);
      setNotice({
        type: "success",
        title: pending.factory
          ? "Система возвращена в заводское состояние"
          : `Сброс выполнен: ${pending.title.toLocaleLowerCase("ru-RU")}`,
        details: pending.factory
          ? `Создан нулевой снимок ${result.zero_backup ?? ""}.`
          : `Страховочная копия: ${result.safety_backup}.`,
      });
    } catch (error) {
      setPending(null);
      setNotice({
        type: "error",
        title: error instanceof Error ? error.message : "Сброс не выполнен",
      });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="competition-reset-layout">
      <div className="competition-reset-intro settings-card">
        <div>
          <span className="reset-shield">
            <ShieldAlert size={22} />
          </span>
          <div>
            <h2>Управление соревнованием</h2>
            <p>
              Каждый тип заполненных данных сбрасывается отдельно. Перед
              удалением автоматически создаётся резервная копия.
            </p>
          </div>
        </div>
        <span className="competition-stage-state">
          {status?.qualification_started
            ? "Соревнование начато"
            : "Этап подготовки"}
        </span>
      </div>
      <div className="competition-reset-grid">
        {ITEMS.map((item) => {
          const Icon = item.icon;
          const count =
            item.countKey && status ? status.counts[item.countKey] : null;
          return (
            <article
              className={
                item.factory ? "reset-card factory-reset-card" : "reset-card"
              }
              key={item.target}
            >
              <div className="reset-card-icon">
                <Icon size={19} />
              </div>
              <div className="reset-card-copy">
                <div>
                  <h3>{item.title}</h3>
                  {count !== null && <span>{count}</span>}
                </div>
                <p>{item.description}</p>
                <small>{item.consequence}</small>
              </div>
              <button
                type="button"
                className="reset-entry-button"
                onClick={() => setPending(item)}
              >
                <RotateCcw size={15} />
                Сбросить
              </button>
            </article>
          );
        })}
      </div>
      {pending && (
        <ConfirmDialog
          title={`Сбросить: ${pending.title.toLocaleLowerCase("ru-RU")}?`}
          description={
            <>
              <strong>Внимательно проверьте действие.</strong>
              <br />
              {pending.consequence}
              <br />
              Перед сбросом будет создана резервная копия текущего состояния.
            </>
          }
          confirmLabel="Сбросить"
          danger
          safeDestructive
          busy={busy}
          onCancel={() => setPending(null)}
          onConfirm={() => void applyReset()}
        />
      )}
      {notice && (
        <RouteToast notification={notice} onClose={() => setNotice(null)} />
      )}
    </div>
  );
}
