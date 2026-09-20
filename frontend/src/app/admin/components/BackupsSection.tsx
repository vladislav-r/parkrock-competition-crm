"use client";

import { ChangeEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  ArchiveRestore,
  CheckCircle2,
  CloudUpload,
  Database,
  Download,
  HardDrive,
  Info,
  Search,
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
import { ListPagination, usePagination } from "./ListPagination";
import { RouteToast, type RouteNotification } from "./RoutesSection";

const SOURCE_LABELS: Partial<Record<BackupItem["source"], string>> = {
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

function sourceLabel(item: BackupItem) {
  return SOURCE_LABELS[item.source] ?? (item.source.startsWith("club-merge-") ? "До объединения клубов" : item.source.startsWith("participant-merge-") ? "До объединения участников" : "Резервная копия");
}

type Action = {
  type: "delete" | "restore";
  item: BackupItem;
  step: 1 | 2;
} | null;

export function BackupsSection({ token }: { token: string }) {
  const [selectedBackup, setSelectedBackup] = useState("");
  const [search, setSearch] = useState("");
  const [source, setSource] = useState("");
  const [oldestFirst, setOldestFirst] = useState(false);
  const [data, setData] = useState<BackupList | null>(null);
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [action, setAction] = useState<Action>(null);
  const [notice, setNotice] = useState<RouteNotification | null>(null);
  const uploadInput = useRef<HTMLInputElement>(null);
  const tableScroll = useRef<HTMLDivElement>(null);

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

  const visibleItems = (data?.items ?? []).filter(item => (!source || item.source === source) && `${new Date(item.created_at).toLocaleString("ru-RU")} ${sourceLabel(item)} ${item.note ?? ""}`.toLocaleLowerCase("ru").includes(search.toLocaleLowerCase("ru"))).sort((a,b) => (new Date(b.created_at).getTime() - new Date(a.created_at).getTime()) * (oldestFirst ? -1 : 1));
  const pagination = usePagination(visibleItems.length, JSON.stringify([search, source, oldestFirst]));
  useEffect(() => { tableScroll.current?.scrollTo({ top: 0 }); }, [pagination.offset, pagination.pageSize, search, source, oldestFirst]);

  return (
    <section className="backups-workspace system-relief">
      <header className="backups-hero">
        <div>
          <h1>Резервные копии</h1>
          <p>Создание, проверка и восстановление данных <span className="backup-admin-label">Только администратор</span></p>
        </div>
      </header>

      <div className="backup-actions-card">
        <input
          value={note}
          maxLength={300}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Комментарий к копии (необязательно)" aria-label="Комментарий к копии"
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
        <p className="backup-safety-note"><Info size={18}/>Перед восстановлением текущая база сохраняется автоматически.</p>
      </div>

      <div className="backup-current-strip">
        <HardDrive size={18} />
        <span>
          <strong>Текущее состояние</strong>
          <small>
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

      <div className="backup-relief-browser">
        <section className="backup-saved-panel">
          <div className="backup-list-head"><div><h2>Сохранённые копии</h2><p>{data?.items.length ?? 0} файлов · {data?.items.filter(item => item.verified_at).length ?? 0} проверены</p></div></div>
          <div className="backup-list-filters">
            <label><Search size={17}/><input data-view-action type="search" aria-label="Найти резервную копию" placeholder="Дата, тип или комментарий" value={search} onChange={e => setSearch(e.target.value)}/></label>
            <select data-view-action aria-label="Тип копии" value={source} onChange={e => setSource(e.target.value)}><option value="">Все типы</option>{Array.from(new Set(data?.items.map(item => item.source))).map(key => <option key={key} value={key}>{sourceLabel(data!.items.find(item => item.source === key)!)}</option>)}</select>
            <button data-view-action className="secondary-button" disabled={Boolean(busy)} onClick={() => void load()}><RefreshCw size={16}/>Обновить</button>
          </div>
          <div ref={tableScroll} className="backup-table-scroll"><table className="backup-saved-table"><thead><tr><th><button data-view-action onClick={() => setOldestFirst(!oldestFirst)}>Дата и время {oldestFirst ? "↑" : "↓"}</button></th><th>Тип</th><th>Размер</th><th>Проверка</th><th>Комментарий</th></tr></thead><tbody>
            {visibleItems.slice(pagination.offset, pagination.offset + pagination.pageSize).map(item => <tr data-view-action key={item.filename} className={selectedBackup === item.filename ? "active" : ""} onClick={() => setSelectedBackup(item.filename)}><td><button data-view-action aria-label={`Открыть копию ${item.filename}`} aria-pressed={selectedBackup === item.filename} onClick={() => setSelectedBackup(item.filename)}>{new Date(item.created_at).toLocaleString("ru-RU", { dateStyle:"short", timeStyle:"short" })}</button></td><td>{sourceLabel(item)}</td><td>{formatBytes(item.size_bytes)}</td><td><span className={item.verified_at ? "backup-verified" : "backup-unverified"}>{item.verified_at && <CheckCircle2 size={16}/>} {item.verified_at ? "Проверена" : "Не проверена"}</span></td><td>{item.note || "—"}</td></tr>)}
          </tbody></table>{data && !visibleItems.length && <p className="backup-list-empty">{data.items.length ? "Копии не найдены" : "Копий пока нет. Создайте первую резервную копию."}</p>}</div>
          <ListPagination {...pagination} label="Резервные копии"/>
        </section>
        <div className="backup-grid">
        {!data?.items.some(item => item.filename === selectedBackup) && <div className="backup-selection-empty"><Database size={28}/><h2>Выберите резервную копию</h2><p>Нажмите на строку слева, чтобы посмотреть состав копии и сравнить с текущими данными.</p></div>}
        {data?.items.filter(item => item.filename === selectedBackup).map((item) => (
          <article className="backup-card" key={item.filename}>
            <div className="backup-card-head">
              <h2>Копия от {new Date(item.created_at).toLocaleString("ru-RU", {dateStyle:"short", timeStyle:"short"})}</h2>
              {item.verified_at ? (
                <span className="backup-verified">
                  <CheckCircle2 size={14} />
                  Проверена
                </span>
              ) : (
                <span className="backup-unverified">Не проверена</span>
              )}
            </div>
            <dl className="backup-detail-meta"><div><dt>Тип копии</dt><dd>{sourceLabel(item)}</dd></div><div><dt>Этап</dt><dd>{item.summary?.event ? STAGE_LABELS[item.summary.event.stage] : "Неизвестно"}</dd></div><div><dt>Комментарий</dt><dd>{item.note || "—"}</dd></div></dl>
            <h3>Сравнение данных</h3>
            {item.summary ? <div className="backup-compare-scroll"><table className="backup-compare-table"><thead><tr><th>Показатель</th><th>В копии</th><th>Сейчас</th><th>Изменение</th></tr></thead><tbody>{Object.entries(COUNT_LABELS).map(([key,label]) => {
              const saved = item.summary!.counts[key]; const current = data?.current.counts[key]; const delta = saved !== undefined && current !== undefined ? current - saved : null;
              return <tr key={key}><td>{label}</td><td>{saved?.toLocaleString("ru-RU") ?? "—"}</td><td>{current?.toLocaleString("ru-RU") ?? "—"}</td><td><span className={delta ? "backup-delta" : ""}>{delta === null || delta === 0 ? "—" : `${delta > 0 ? "↑ +" : "↓ −"}${Math.abs(delta).toLocaleString("ru-RU")}`}</span></td></tr>;
            })}</tbody></table></div> : <p className="backup-empty-summary">Проверьте копию, чтобы увидеть её состав и отличие от текущей базы.</p>}
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
                Восстановить эту копию
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

      </div>

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
