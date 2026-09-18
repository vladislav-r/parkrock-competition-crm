"use client";
import { useState } from "react";
import { EventInfo, updatePublicRefresh } from "@/lib/api";
import { PUBLIC_DISPLAY_DEFAULTS, PublicDisplaySettings } from "@/lib/public-display";
import { SettingHelp } from "./SettingHelp";

type Draft = { qualification_refresh_seconds: number; final_refresh_seconds: number; public_display_settings: PublicDisplaySettings; expected_version: number };
export function PublicRefreshSettings({ event, token, onSaved }: { event: EventInfo; token: string; onSaved: () => Promise<void> }) {
  const [draft, setDraft] = useState<Draft | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const values = draft ?? { qualification_refresh_seconds: event.qualification_refresh_seconds, final_refresh_seconds: event.final_refresh_seconds, public_display_settings: { ...PUBLIC_DISPLAY_DEFAULTS, ...event.public_display_settings }, expected_version: event.version };
  const display = values.public_display_settings;
  function change<K extends keyof PublicDisplaySettings>(key: K, value: PublicDisplaySettings[K]) {
    setDraft({ ...values, public_display_settings: { ...display, [key]: value } }); setMessage("");
  }
  function number(key: keyof PublicDisplaySettings, label: string, help: string, min: number, max: number) {
    return <div className="public-setting-field" key={key}><div className="public-setting-label"><label htmlFor={`display-${key}`}>{label}</label><SettingHelp label={label}>{help}</SettingHelp></div>
      <input id={`display-${key}`} type="number" min={min} max={max} step={1} required value={Number.isNaN(display[key]) ? "" : display[key] as number} disabled={saving} onChange={e => change(key, e.target.valueAsNumber)}/><small>{min}–{max}</small></div>;
  }
  function toggle(key: "tv_teams" | "sponsors_enabled" | "tv_sponsors_enabled", label: string, help: string) {
    return <div className="public-setting-check"><label><input type="checkbox" checked={display[key]} disabled={saving} onChange={e => change(key, e.target.checked)}/>{label}</label><SettingHelp label={label}>{help}</SettingHelp></div>;
  }
  return <form className="public-display-form" onSubmit={async e => {
    e.preventDefault(); setSaving(true); setMessage("");
    try { await updatePublicRefresh(token, values); await onSaved(); setDraft(null); setMessage("Настройки показа сохранены"); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Не удалось сохранить настройки"); }
    finally { setSaving(false); }
  }}>
    <section className="settings-card"><div className="settings-card-head"><div><h2>Обновление результатов</h2><p>Частота публикации и получения результатов зрителями.</p></div></div><div className="public-settings-grid">
      {([['qualification_refresh_seconds', 'Квалификация, сек.', 'Интервал сборки общей публикации на подготовке и квалификации, а также запросов страниц квалификации. Главная и сеты следуют текущему этапу. Новый результат появляется после сборки и следующего запроса страницы — задержка может достигать суммы этих интервалов.'], ['final_refresh_seconds', 'Финал, сек.', 'Интервал сборки общей публикации во время финала и после завершения, а также запросов страниц финала. Меньшее значение даёт более частое обновление и увеличивает нагрузку. Настройка действует также на ТВ.']] as const).map(([key, label, help]) => <div className="public-setting-field" key={key}><div className="public-setting-label"><label htmlFor={key}>{label}</label><SettingHelp label={label}>{help}</SettingHelp></div><input id={key} type="number" min={3} max={300} step={1} required value={Number.isNaN(values[key]) ? "" : values[key]} disabled={saving} onChange={e => { setDraft({ ...values, [key]: e.target.valueAsNumber }); setMessage(""); }}/><small>3–300</small></div>)}
    </div></section>
    <section className="settings-card"><div className="settings-card-head"><div><h2>ТВ · начало показа</h2><p>Значения для нового экрана. Параметры сохранённой ссылки имеют приоритет.</p></div><a href="/tv" target="_blank" rel="noreferrer" data-view-action>Открыть ТВ ↗</a></div>
      <div className="public-settings-grid">{number("tv_interval_seconds", "Время одного экрана, сек.", "Сколько секунд показывать таблицу перед переходом к следующей странице или группе. Это время смены экранов, а не обновления результатов. На странице ТВ его можно изменить для конкретного экрана.", 5, 120)}
      <div className="public-setting-field"><div className="public-setting-label"><label htmlFor="tv-default-stage">Начальный этап</label><SettingHelp label="Начальный этап">Этап при открытии новой страницы ТВ без заданного этапа в ссылке. Если финал ещё не опубликован, экран будет ожидать его результаты.</SettingHelp></div><select id="tv-default-stage" value={display.tv_stage} disabled={saving} onChange={e => change("tv_stage", e.target.value as PublicDisplaySettings["tv_stage"])}><option value="qualification">Квалификация</option><option value="final">Финал</option></select></div></div>
      {toggle("tv_teams", "Добавлять командный зачёт", "Включать командный зачёт при настройке нового ТВ-экрана. Команды появятся после подтверждения итогов выбранного этапа. На странице ТВ можно изменить выбор групп и команд.")}
    </section>
    <section className="settings-card"><div className="settings-card-head"><div><h2>ТВ · таблицы и управление</h2><p>Общие параметры для всех ТВ-экранов.</p></div></div><div className="public-settings-grid">
      {number("tv_rows_per_column", "Максимум строк в колонке", "Верхний предел числа участников в одной колонке. Если высоты экрана недостаточно, строк будет меньше. Остальные участники перейдут на следующие экраны.", 5, 30)}
      {number("tv_max_columns", "Максимум колонок", "Одна или две таблицы рядом. На узком экране всегда используется одна колонка, чтобы имена оставались читаемыми.", 1, 2)}
      {number("tv_highlight_top", "Выделять первые места", "Сколько первых мест выделять цветом в квалификации. Укажите 0, чтобы отключить выделение. Это оформление, оно не влияет на список финалистов. В финале выделяются три призовых места.", 0, 100)}
      {number("tv_controls_hide_seconds", "Скрывать управление через, сек.", "Через сколько секунд без движения указателя, нажатий или касаний скрывать панель управления ТВ. Любое действие снова показывает панель.", 1, 30)}
    </div></section>
    <section className="settings-card"><div className="settings-card-head"><div><h2>Партнёры · сайт</h2><p>Ленты логотипов на публичных страницах.</p></div></div>
      {toggle("sponsors_enabled", "Показывать партнёров на сайте", "Показывать обе ленты партнёров на главной, в сетах, результатах, абсолюте и командном зачёте. Показ на ТВ настраивается отдельно.")}
      <div className="public-settings-grid">{number("sponsor_featured_seconds", "Цикл верхнего ряда, сек.", "Время полного прохода верхней ленты основных партнёров. Чем больше значение, тем медленнее движение. При ограничении анимации на устройстве ленты остаются неподвижными.", 10, 300)}{number("sponsor_regular_seconds", "Цикл нижнего ряда, сек.", "Время полного прохода нижней ленты партнёров. Чем больше значение, тем медленнее движение.", 10, 300)}</div>
    </section>
    <section className="settings-card"><div className="settings-card-head"><div><h2>Партнёры · ТВ</h2><p>Отдельная видимость и скорость для больших экранов.</p></div></div>
      {toggle("tv_sponsors_enabled", "Показывать партнёров на ТВ", "Показывать обе ленты партнёров во время ТВ-показа. Если выключить, освободившееся место займёт таблица результатов.")}
      <div className="public-settings-grid">{number("tv_sponsor_featured_seconds", "Цикл верхнего ряда ТВ, сек.", "Время полного прохода верхней ленты на ТВ. Чем больше значение, тем медленнее движение.", 10, 300)}{number("tv_sponsor_regular_seconds", "Цикл нижнего ряда ТВ, сек.", "Время полного прохода нижней ленты на ТВ. Не влияет на скорость ленты обычного сайта.", 10, 300)}</div>
    </section>
    <div className="public-settings-save"><p>Открытые страницы получат изменения при следующем обновлении. Начальные настройки ТВ применяются при новом открытии.</p><button className="primary-action" disabled={saving || !draft}>{saving ? "Сохранение…" : "Сохранить настройки показа"}</button>
      {draft && draft.expected_version !== event.version && <p role="status">Настройки изменились у другого сотрудника. <button type="button" className="secondary-action" onClick={() => { setDraft(null); setMessage(""); }}>Загрузить актуальные настройки</button></p>}
      {message && <p role="status">{message}</p>}
    </div>
  </form>;
}
