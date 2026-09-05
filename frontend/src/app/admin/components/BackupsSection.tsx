"use client";

import { ChangeEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  ArchiveRestore,
  CheckCircle2,
  CloudUpload,
  Database,
  Download,
  HardDrive,
  Plus,
  RefreshCw,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import {
  BackupItem,
  BackupList,
  createBackup,
  deleteBackup,
  downloadBackup,
  getBackups,
  restoreBackup,
  uploadBackup,
  verifyBackup,
} from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";
import { RouteToast, type RouteNotification } from "./RoutesSection";

const SOURCE_LABELS: Record<BackupItem["source"], string> = {
  manual: "Ручная",
  automatic: "Автоматическая",
  "pre-restore": "Страховочная",
  "pre-reset": "Перед сбросом",
  "factory-zero": "Нулевая",
  "stage-transition": "Переход этапа",
  "pre-rollback": "Перед откатом",
  upload: "Загруженная",
  legacy: "Ранее созданная",
};
const STAGE_LABELS = {
  preparation: "Подготовка",
  qualification: "Квалификация",
  final: "Финал",
  completed: "Завершён",
};
const COUNT_LABELS: Record<string, string> = {
  participants: "Участники",
  clubs: "Клубы",
  applications: "Заявки",
  ascents: "Пролазы",
  final_category_results: "Финалисты",
  final_route_attempts: "Результаты финала",
};

function formatBytes(value: number) {
  if (value < 1024) return `${value} Б`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} КБ`;
  if (value < 1024 * 1024 * 1024)
    return `${(value / 1024 / 1024).toFixed(1)} МБ`;
  return `${(value / 1024 / 1024 / 1024).toFixed(2)} ГБ`;
}

function differenceText(value: number) {
  if (value === 0) return "как сейчас";
  return value > 0 ? `на ${value} больше` : `на ${Math.abs(value)} меньше`;
}

type Action = {
  type: "delete" | "restore";
  item: BackupItem;
  step: 1 | 2;
} | null;

export function BackupsSection({ token }: { token: string }) {
  const [data, setData] = useState<BackupList | null>(null);
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [action, setAction] = useState<Action>(null);
  const [notice, setNotice] = useState<RouteNotification | null>(null);
  const uploadInput = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setData(await getBackups(token));
    } catch (error) {
      setNotice({
        type: "error",
        title:
          error instanceof Error
            ? error.message
            : "Не удалось загрузить резервные копии",
      });
    }
  }, [token]);
  useEffect(() => {
    void load();
  }, [load]);

  async function run(
    label: string,
    callback: () => Promise<unknown>,
    success: string,
  ) {
    setBusy(label);
    setNotice(null);
    try {
      await callback();
      await load();
      setNotice({ type: "success", title: success });
    } catch (error) {
      setNotice({
        type: "error",
        title:
          error instanceof Error
            ? error.message
            : "Операция завершилась с ошибкой",
      });
    } finally {
      setBusy("");
    }
  }

  async function create() {
    await run(
      "create",
      () => createBackup(token, note),
      "Резервная копия создана и проверена",
    );
    setNote("");
  }

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    await run(
      "upload",
      () => uploadBackup(token, file, `Загружен файл ${file.name}`),
      "Копия загружена, восстановлена во временную базу и проверена",
    );
  }

  async function applyAction() {
    if (!action) return;
    if (action.type === "restore" && action.step === 1) {
      setAction({ ...action, step: 2 });
      setConfirmation("");
      return;
    }
    const item = action.item;
    const type = action.type;
    setAction(null);
    if (type === "delete")
      await run(
        item.filename,
        () => deleteBackup(token, item.filename, confirmation),
        "Резервная копия удалена",
      );
    else
      await run(
        item.filename,
        async () => {
          const result = await restoreBackup(
            token,
            item.filename,
            confirmation,
          );
          setNotice({
            type: "success",
            title: "База восстановлена",
            details: `Перед откатом сохранена страховочная копия ${result.safety_backup.filename}.`,
          });
        },
        "База восстановлена",
      );
    setConfirmation("");
  }

  const expectedConfirmation =
    action?.type === "delete"
      ? "УДАЛИТЬ"
      : action
        ? `ВОССТАНОВИТЬ ${action.item.filename}`
        : "";

  return (
    <section className="backups-workspace">
      <header className="backups-hero">
        <div>
          <div className="eyebrow">Система · только администратор</div>
          <h1>Резервные копии</h1>
          <p>
            Создание, проверка и безопасное восстановление PostgreSQL. Перед
            каждым откатом текущая база сохраняется автоматически.
          </p>
        </div>
        <div className="backup-health">
          <ShieldCheck size={22} />
          <span>
            <strong>
              {data?.items.filter((item) => item.verified_at).length ?? 0}
            </strong>
            <small>проверенных копий</small>
          </span>
        </div>
      </header>

      <div className="backup-actions-card">
        <div>
          <h2>
            <Plus size={18} />
            Создать копию сейчас
          </h2>
          <p>
            Система снимет всю базу, рассчитает контрольную сумму и проверит
            структуру архива.
          </p>
        </div>
        <input
          value={note}
          maxLength={300}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Комментарий, например: перед запуском финала"
        />
        <button
          className="primary-action"
          disabled={Boolean(busy)}
          onClick={() => void create()}
        >
          <Database size={16} />
          {busy === "create" ? "Создаём…" : "Создать и проверить"}
        </button>
        <input
          ref={uploadInput}
          type="file"
          accept=".dump,application/octet-stream"
          hidden
          onChange={(event) => void upload(event)}
        />
        <button
          className="secondary-button"
          disabled={Boolean(busy)}
          onClick={() => uploadInput.current?.click()}
        >
          <CloudUpload size={16} />
          {busy === "upload" ? "Проверяем…" : "Загрузить .dump"}
        </button>
      </div>

      <div className="backup-current-strip">
        <HardDrive size={18} />
        <span>
          <strong>Текущее состояние</strong>
          <small>
            {data?.current.event?.title ?? "Фестиваль не найден"} ·{" "}
            {data?.current.event ? STAGE_LABELS[data.current.event.stage] : "—"}
          </small>
        </span>
        <div>
          {Object.entries(data?.current.counts ?? {})
            .filter(([key]) => key in COUNT_LABELS)
            .map(([key, value]) => (
              <span key={key}>
                <small>{COUNT_LABELS[key]}</small>
                <strong>{value}</strong>
              </span>
            ))}
        </div>
      </div>

      <div className="backup-list-head">
        <div>
          <h2>Сохранённые копии</h2>
          <p>{data?.items.length ?? 0} файлов · новые сверху</p>
        </div>
        <button
          className="compact-action"
          disabled={Boolean(busy)}
          onClick={() => void load()}
        >
          <RefreshCw size={15} />
          Обновить
        </button>
      </div>
      <div className="backup-grid">
        {data?.items.map((item) => (
          <article className="backup-card" key={item.filename}>
            <div className="backup-card-head">
              <div className={`backup-source ${item.source}`}>
                <Database size={15} />
                {SOURCE_LABELS[item.source]}
              </div>
              {item.verified_at ? (
                <span className="backup-verified">
                  <CheckCircle2 size={14} />
                  Проверена
                </span>
              ) : (
                <span className="backup-unverified">Не проверена</span>
              )}
            </div>
            <h3>{new Date(item.created_at).toLocaleString("ru-RU")}</h3>
            <code>{item.filename}</code>
            <div className="backup-meta">
              <span>
                <small>Размер</small>
                <strong>{formatBytes(item.size_bytes)}</strong>
              </span>
              <span>
                <small>Стадия</small>
                <strong>
                  {item.summary?.event
                    ? STAGE_LABELS[item.summary.event.stage]
                    : "Неизвестно"}
                </strong>
              </span>
            </div>
            {item.note && <p className="backup-note">{item.note}</p>}
            {item.summary ? (
              <div className="backup-comparison">
                {Object.entries(item.summary.counts)
                  .filter(([key]) => key in COUNT_LABELS)
                  .map(([key, value]) => (
                    <div key={key}>
                      <span>{COUNT_LABELS[key]}</span>
                      <strong>{value}</strong>
                      <small
                        className={
                          (item.differences?.[key] ?? 0) === 0
                            ? "same"
                            : "changed"
                        }
                      >
                        {item.differences?.[key] === undefined
                          ? ""
                          : differenceText(item.differences[key])}
                      </small>
                    </div>
                  ))}
              </div>
            ) : (
              <div className="backup-empty-summary">
                Проверьте копию, чтобы увидеть её состав и отличие от текущей
                базы.
              </div>
            )}
            {item.checksum_sha256 && (
              <div className="backup-checksum" title={item.checksum_sha256}>
                SHA-256 · {item.checksum_sha256.slice(0, 16)}…
              </div>
            )}
            <div className="backup-card-actions">
              <button
                disabled={Boolean(busy)}
                onClick={() => void downloadBackup(token, item.filename)}
                title="Скачать"
              >
                <Download size={16} />
                Скачать
              </button>
              <button
                disabled={Boolean(busy)}
                onClick={() =>
                  void run(
                    item.filename,
                    () => verifyBackup(token, item.filename),
                    "Копия успешно восстановлена во временную базу и проверена",
                  )
                }
              >
                <ShieldCheck size={16} />
                {busy === item.filename ? "Проверяем…" : "Проверить"}
              </button>
              <button
                className="restore-backup-button"
                disabled={Boolean(busy)}
                onClick={() => {
                  setAction({ type: "restore", item, step: 1 });
                  setConfirmation("");
                }}
              >
                <ArchiveRestore size={16} />
                Восстановить
              </button>
              <button
                className="delete-backup-button"
                disabled={Boolean(busy)}
                onClick={() => {
                  setAction({ type: "delete", item, step: 1 });
                  setConfirmation("");
                }}
                title="Удалить"
              >
                <Trash2 size={16} />
              </button>
            </div>
          </article>
        ))}
        {data && data.items.length === 0 && (
          <div className="backup-empty">
            <Database size={28} />
            <h2>Копий пока нет</h2>
            <p>Создайте первую резервную копию перед началом работы.</p>
          </div>
        )}
      </div>

      {action && (
        <ConfirmDialog
          title={
            action.type === "delete"
              ? "Удалить резервную копию?"
              : action.step === 1
                ? "Восстановить эту версию базы?"
                : "Последнее подтверждение восстановления"
          }
          description={
            action.type === "delete" ? (
              <>
                Файл <strong>{action.item.filename}</strong> будет удалён без
                возможности восстановления.
              </>
            ) : action.step === 1 ? (
              <>
                Рабочие данные будут заменены состоянием от{" "}
                <strong>
                  {new Date(action.item.created_at).toLocaleString("ru-RU")}
                </strong>
                . Сначала система проверит копию и сохранит текущую базу.
              </>
            ) : (
              <>
                Введите точную фразу ниже. Во время восстановления внесение
                результатов будет кратковременно недоступно.
              </>
            )
          }
          confirmLabel={
            action.type === "restore" && action.step === 1
              ? "Продолжить"
              : action.type === "delete"
                ? "Удалить файл"
                : "Восстановить базу"
          }
          danger
          busy={Boolean(busy)}
          confirmDisabled={
            (action.type === "delete" || action.step === 2) &&
            confirmation !== expectedConfirmation
          }
          onCancel={() => {
            setAction(null);
            setConfirmation("");
          }}
          onConfirm={() => void applyAction()}
        >
          {(action.type === "delete" || action.step === 2) && (
            <label className="typed-confirmation">
              Для подтверждения введите:<code>{expectedConfirmation}</code>
              <input
                autoFocus
                value={confirmation}
                onChange={(event) => setConfirmation(event.target.value)}
                placeholder={expectedConfirmation}
              />
            </label>
          )}
        </ConfirmDialog>
      )}
      {notice && (
        <RouteToast notification={notice} onClose={() => setNotice(null)} />
      )}
    </section>
  );
}
