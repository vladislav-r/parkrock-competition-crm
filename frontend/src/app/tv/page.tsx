"use client";

import Link from "next/link";
import { Copy, Maximize, Medal, Monitor, Pause, Play, Settings } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { ApiError, getPublicFinalResults, getPublicResults, groupSlug } from "@/lib/api";
import { nextTvGroup, paginateTv, readTvSettings, tvQuery, TvGroup, TvRow, TvScreen, TvSettings } from "@/lib/tv";
import SponsorStrip from "../components/SponsorStrip";
import "./tv.css";
import { publicRefreshMs } from "@/lib/public-refresh";

type Feed = { title: string; groups: TvGroup[]; available: string[]; finalAvailable: boolean; message: string };
const medals = { gold: "Золото", silver: "Серебро", bronze: "Бронза" };

function Table({ rows, stage }: { rows: TvRow[]; stage: TvSettings["stage"] }) {
  return <table className="qualification-table tv-table">
    <colgroup><col className="tv-place-col"/><col className="tv-name-col"/><col className="tv-club-col"/><col className="tv-medal-col"/><col className="tv-score-col"/></colgroup>
    <thead><tr><th scope="col">№</th><th scope="col">Участник</th><th scope="col">Клуб</th><th scope="col">Медаль</th><th scope="col">Очки</th></tr></thead>
    <tbody>{rows.map(row => {
      const leader = stage === "qualification" && row.place !== null && row.place <= 10;
      const podium = stage === "final" && row.place !== null && row.place <= 3;
      return <tr key={row.participant_id} data-participant={row.participant_id} className={leader ? "tv-leader" : podium ? `tv-podium tv-place-${row.place}` : undefined}>
      <td>{row.place !== null ? podium ? <span className={`final-place place-${row.place}`}>{row.place}</span> : <strong>{row.place}</strong> : "—"}</td>
      <td className="tv-name">{row.full_name}</td><td className="tv-club">{row.club}</td>
      <td className="tv-medal">{row.medal ? <span className={`finisher-medal ${row.medal}`} aria-label={`Медаль за очки · ${medals[row.medal]}`}><Medal/><small>{medals[row.medal]}</small></span> : <span aria-hidden="true">—</span>}</td>
      <td className="tv-score">{row.points?.toLocaleString("ru-RU", { maximumFractionDigits: stage === "final" ? 1 : 10 }) ?? "—"}</td>
    </tr>;})}</tbody>
  </table>;
}

export default function TvPage() {
  const [settings, setSettings] = useState<TvSettings | null>(null);
  const [playing, setPlaying] = useState(false);
  const [paused, setPaused] = useState(false);
  const [feed, setFeed] = useState<Feed | null>(null);
  const latest = useRef<Feed | null>(null);
  const [snapshot, setSnapshot] = useState<TvGroup | null>(null);
  const [screens, setScreens] = useState<TvScreen[]>([]);
  const [page, setPage] = useState(0);
  const [offline, setOffline] = useState(false);
  const [updated, setUpdated] = useState<Date | null>(null);
  const [controls, setControls] = useState(true);
  const [notice, setNotice] = useState("");
  const [shareLink, setShareLink] = useState("");
  const area = useRef<HTMLDivElement>(null);
  const single = useRef<HTMLDivElement>(null);
  const half = useRef<HTMLDivElement>(null);
  const controlsTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    function restore() {
      const params = new URLSearchParams(window.location.search);
      setSettings(readTvSettings(params)); setPlaying(params.get("autoplay") === "1");
      setSnapshot(null); setPaused(false); setPage(0); setFeed(null); latest.current = null;
    }
    restore();
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, []);

  useEffect(() => {
    if (!settings) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let refreshMs = publicRefreshMs(null, settings.stage);
    const controller = new AbortController();
    // Recursive polling never overlaps; timeout also recovers a stalled connection.
    async function load() {
      const signal = AbortSignal.any([controller.signal, AbortSignal.timeout(10000)]);
      try {
        const data = await getPublicResults("", "", signal);
        refreshMs = publicRefreshMs(data, settings!.stage);
        const finalAvailable = data.stage === "final" || data.stage === "completed";
        const available = settings!.stage === "final" ? data.groups.filter(name => data.final_groups.includes(name)) : data.groups;
        const selected = available.filter(name => settings!.groups === null || settings!.groups.includes(groupSlug(name)));
        const groups: TvGroup[] = [];
        if (settings!.stage === "qualification") {
          selected.forEach(name => groups.push({ name, slug: groupSlug(name), rows: data.results.filter(row => row.group_name === name) }));
        } else if (finalAvailable) {
          // A small bounded sequence avoids issuing one burst of requests per category.
          for (const name of selected) {
            try {
              const result = await getPublicFinalResults(name, signal);
              groups.push({ name, slug: groupSlug(name), rows: result.results.map(row => ({
                participant_id: row.participant_id, full_name: row.full_name, club: row.club,
                place: row.place, points: row.score, medal: null, is_finalist: false,
              })) });
            } catch (reason) {
              if (!(reason instanceof ApiError && (reason.status === 400 || reason.status === 404))) throw reason;
            }
          }
        }
        if (stopped) return;
        const message = settings!.stage === "final" && !finalAvailable ? "Финал пока недоступен. Ожидаем публикацию данных." : settings!.groups !== null && !selected.length ? "Выбранные группы недоступны. Измените выбор в настройках или дождитесь публикации." : "Нет данных для показа";
        const next = { title: data.event_title, available, finalAvailable, groups: groups.filter(group => group.rows.length), message };
        latest.current = next; setFeed(next); setOffline(false); setUpdated(new Date());
      } catch (reason) {
        if (stopped) return;
        if (reason instanceof ApiError && reason.status === 404) {
          const next = { title: "Онлайн-результаты", available: [], finalAvailable: false, groups: [], message: "Нет опубликованного соревнования. Ожидаем данные." };
          latest.current = next; setFeed(next); setOffline(false); setUpdated(new Date());
        } else setOffline(true);
      } finally {
        if (!stopped) timer = setTimeout(load, refreshMs);
      }
    }
    void load();
    return () => { stopped = true; controller.abort(); clearTimeout(timer); };
  }, [settings]);

  useEffect(() => {
    if (!playing) return;
    if (!feed) return;
    if (!snapshot && feed.groups.length) { setSnapshot(feed.groups[0]); setPage(0); }
    // Do not retain a final group whose publication/participation was withdrawn.
    else if (snapshot && (!feed.available.length || (settings?.stage === "final" && !feed.available.includes(snapshot.name)))) setSnapshot(null);
  }, [feed, playing, snapshot, settings?.stage]);

  useLayoutEffect(() => {
    if (!playing || !snapshot || !area.current || !single.current || !half.current) return;
    let cancelled = false;
    function measure() {
      if (cancelled || !area.current || !single.current || !half.current) return;
      const next = paginateTv(snapshot!.rows.length);
      const probe = snapshot!.rows.length > 20 ? half.current : single.current;
      const available = area.current.clientHeight - 2;
      let font = available / 29;
      // Use one size for the entire group, including its last, partially filled screen.
      // Measure every 20-row column so wrapped names cannot push a column off screen.
      for (let attempt = 0; attempt < 5; attempt++) {
        area.current.style.setProperty("--tv-font", `${font}px`);
        const heights = Array.from(probe.querySelectorAll("tbody tr"), row => row.getBoundingClientRect().height);
        const header = probe.querySelector("thead")!.getBoundingClientRect().height;
        let tallest = 0;
        for (let start = 0; start < heights.length; start += 20) {
          tallest = Math.max(tallest, header + heights.slice(start, start + 20).reduce((sum, height) => sum + height, 0));
        }
        if (tallest <= available) break;
        font *= available / tallest * .98;
      }
      setScreens(next); setPage(0);
    }
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(area.current);
    void document.fonts.ready.then(measure);
    return () => { cancelled = true; observer.disconnect(); };
  }, [snapshot, playing]);

  useEffect(() => {
    if (!playing || paused || !snapshot || !screens.length || !settings) return;
    const timer = setTimeout(() => {
      if (page + 1 < screens.length) setPage(page + 1);
      else {
        const next = nextTvGroup(latest.current?.groups ?? [], snapshot.slug);
        setSnapshot(next ? { ...next } : null); setPage(0);
      }
    }, settings.interval * 1000);
    return () => clearTimeout(timer);
  }, [playing, paused, snapshot, screens, page, settings]);

  useEffect(() => {
    if (!playing) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function reveal() {
      setControls(true);
      if (controlsTimer.current) clearTimeout(controlsTimer.current);
      controlsTimer.current = setTimeout(() => setControls(false), 3000);
    }
    reveal();
    window.addEventListener("pointermove", reveal);
    window.addEventListener("pointerdown", reveal);
    window.addEventListener("keydown", reveal);
    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener("pointermove", reveal); window.removeEventListener("pointerdown", reveal); window.removeEventListener("keydown", reveal);
      if (controlsTimer.current) clearTimeout(controlsTimer.current);
    };
  }, [playing]);

  function change(next: TvSettings) {
    setSettings(next); setShareLink(""); setNotice(""); setSnapshot(null);
    latest.current = null;
    setFeed(previous => next.stage !== settings?.stage || !previous ? null : { ...previous, groups: [], message: "Обновляем выбор групп…" });
  }
  async function fullscreen() {
    try {
      if (!document.fullscreenElement) await document.documentElement.requestFullscreen();
      else await document.exitFullscreen();
    } catch { setNotice("Полный экран недоступен — показ продолжается в окне."); }
  }
  function start() {
    if (!settings) return;
    window.history.pushState(null, "", `/tv?${tvQuery(settings, true)}`);
    setPaused(false); setPage(0); setSnapshot(null); setPlaying(true); setNotice("");
    void fullscreen();
  }
  async function copyLink() {
    if (!settings) return;
    const url = `${window.location.origin}/tv?${tvQuery(settings, true)}`;
    try { await navigator.clipboard.writeText(url); setNotice("Ссылка скопирована"); }
    catch { setShareLink(url); setNotice("Скопируйте ссылку из поля ниже."); }
  }
  function configure() {
    setPlaying(false); setPaused(false); setSnapshot(null); setNotice("");
    if (settings) window.history.pushState(null, "", `/tv?${tvQuery(settings, false)}`);
    if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
  }

  if (!settings) return <main className="tv-loading">Загрузка режима ТВ…</main>;
  const screen = screens[page];
  const status = `${offline ? "Нет связи" : updated ? "Данные обновлены" : "Загрузка данных"}${updated ? ` · ${updated.toLocaleTimeString("ru-RU")}` : ""}`;
  const stageTitle = settings.stage === "final" ? "Финал" : "Квалификация";
  const groupNumber = snapshot ? Math.max(1, (feed?.groups.findIndex(group => group.slug === snapshot.slug) ?? 0) + 1) : 0;

  if (!playing) return <main className="qualification-page tv-setup">
    <header className="tv-setup-header"><Link href="/">← Онлайн-результаты</Link><img src="/brand/parkrock-black.svg" alt="ПаркРок"/></header>
    <section className="tv-settings">
      <div className="tv-kicker"><Monitor size={20}/> На большом экране</div>
      <h1>Режим ТВ</h1><p>Результаты сменяются автоматически. Выберите группы и начните показ.</p>
      <form onSubmit={event => { event.preventDefault(); start(); }}>
        <div className="tv-fields"><label>Этап<select value={settings.stage} onChange={event => change({ ...settings, stage: event.target.value as TvSettings["stage"] })}><option value="qualification">Квалификация</option><option value="final" disabled={!feed?.finalAvailable && settings.stage !== "final"}>Финал{!feed?.finalAvailable ? " — пока недоступен" : ""}</option></select></label>
          <label>Время экрана, секунд<input type="number" min={5} max={120} step={1} required value={settings.interval} onChange={event => setSettings({ ...settings, interval: Number(event.target.value) })}/><small>От 5 до 120 секунд</small></label></div>
        <fieldset><legend>Возрастные группы</legend>
          <label className="tv-choice tv-all"><input type="checkbox" checked={settings.groups === null} onChange={event => change({ ...settings, groups: event.target.checked ? null : [] })}/>Все группы<small>Новые группы добавятся автоматически</small></label>
          <div className="tv-group-choices">{feed?.available.map(name => {
            const slug = groupSlug(name);
            return <label className="tv-choice" key={name}><input type="checkbox" checked={settings.groups === null || settings.groups.includes(slug)} onChange={event => {
              const current = settings.groups ?? feed.available.map(groupSlug);
              change({ ...settings, groups: event.target.checked ? [...current, slug] : current.filter(value => value !== slug) });
            }}/>{name}</label>;
          })}</div>
          {settings.groups !== null && !settings.groups.length && <p className="tv-note">Выберите хотя бы одну группу.</p>}
          {feed && !feed.groups.length && <p className="tv-note">{feed.message}</p>}
        </fieldset>
        <div className="tv-actions"><button className="tv-primary" type="submit" disabled={settings.groups?.length === 0}><Play size={19}/>Начать показ</button><button type="button" onClick={() => void copyLink()} disabled={!Number.isInteger(settings.interval) || settings.interval < 5 || settings.interval > 120 || settings.groups?.length === 0}><Copy size={18}/>Скопировать ссылку</button></div>
      </form>
      {notice && <p role="status">{notice}</p>}{shareLink && <input className="tv-share" aria-label="Ссылка на показ" readOnly value={shareLink} onFocus={event => event.target.select()}/>}
      <p className="tv-help">После запуска откроется полный экран. Движение мыши или касание покажет управление. Перед мероприятием отключите сон и гашение экрана на устройстве.</p>
      <div className={offline ? "tv-offline" : "tv-connection"} role="status">{status}</div>
    </section>
    <SponsorStrip/>
  </main>;

  return <main className="qualification-page tv-player">
    <header className="tv-header"><div className="tv-brand"><img src="/brand/parkrock-white.svg" alt="ПаркРок"/></div><div className="tv-heading"><h1>{snapshot?.name ?? "Режим ТВ"}</h1><div className="tv-stage">{stageTitle}</div></div><div className={`tv-live${offline ? " is-offline" : ""}`}><i/>{offline ? "Нет связи" : "Прямой эфир"}</div></header>
    <section className="tv-partners"><span>Партнёры</span><SponsorStrip/></section>
    <div className="tv-highlight-note">{settings.stage === "qualification" ? "Топ-10 — лидеры квалификации" : "1–3 места — призёры финала"}</div>
    <div className="tv-results" ref={area}>
      {snapshot ? <>
        <div className="tv-measure tv-measure-single" ref={single} aria-hidden="true"><Table rows={snapshot.rows} stage={settings.stage}/></div>
        <div className="tv-measure tv-measure-half" ref={half} aria-hidden="true"><Table rows={snapshot.rows} stage={settings.stage}/></div>
        {screen ? <div className={`tv-columns${screen.right ? " tv-two" : ""}`}>
          <Table rows={snapshot.rows.slice(...screen.left)} stage={settings.stage}/>
          {screen.right && (screen.right[0] < screen.right[1] ? <Table rows={snapshot.rows.slice(...screen.right)} stage={settings.stage}/> : <div/>)}
        </div> : <div className="tv-empty">Увеличьте размер окна для показа таблицы.</div>}
      </> : <div className="tv-empty"><Monitor/><h2>{feed?.message ?? "Ожидаем загрузку результатов"}</h2><p>Проверяем появление данных автоматически</p></div>}
    </div>
    <footer className="tv-footer">
      <span className="tv-medal-legend"><b>Медали за очки:</b>{Object.entries(medals).map(([medal, label]) => <span key={medal} className={medal}><Medal/>{label}</span>)}</span>
      <span className="tv-cycle"><i key={`${snapshot?.slug}-${page}-${paused}`} className={paused ? "is-paused" : ""} style={{ animationDuration: `${settings.interval}s` }}/><b>{paused ? "Пауза" : `Смена каждые ${settings.interval} с`}</b>{snapshot && <>Экран {page + 1} / {screens.length} · Группа {groupNumber} / {feed?.groups.length ?? 0}</>}</span>
      <span className="tv-update" role="status">{status}</span>
    </footer>
    <div className={`tv-controls${controls ? " is-visible" : ""}`} aria-label="Управление показом" onMouseDown={event => event.preventDefault()}>
      <button onClick={() => setPaused(value => !value)}>{paused ? <Play/> : <Pause/>}{paused ? "Продолжить" : "Пауза"}</button>
      <button onClick={() => void fullscreen()}><Maximize/>Полный экран</button><button onClick={configure}><Settings/>Настройки</button>
      {notice && <span role="status">{notice}</span>}
    </div>
  </main>;
}
