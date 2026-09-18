import type { Medal } from "./api";
import { PUBLIC_DISPLAY_DEFAULTS, type PublicDisplaySettings } from "./public-display";

export type TvSettings = { stage: "qualification" | "final"; interval: number; teams?: boolean; groups: string[] | null };
export type TvRow = { participant_id: string; full_name: string; club: string; place: number | null; points: number | null; medal: Medal | null; is_finalist: boolean };
export type TvGroup = { name: string; slug: string; teams?: boolean; rows: TvRow[] };
export type TvScreen = { left: [number, number]; right?: [number, number] };

export function readTvSettings(params: URLSearchParams, defaults: PublicDisplaySettings = PUBLIC_DISPLAY_DEFAULTS): TvSettings {
  const interval = Number(params.get("interval"));
  return {
    ...(params.get("teams") === "1" || (!params.has("teams") && !params.has("stage") && !params.has("interval") && defaults.tv_teams) ? { teams: true } : {}),
    stage: params.has("stage") ? params.get("stage") === "final" ? "final" : "qualification" : defaults.tv_stage,
    interval: Number.isInteger(interval) && interval >= 5 && interval <= 120 ? interval : defaults.tv_interval_seconds,
    groups: params.get("groups") === "all" || !params.has("group") ? null : [...new Set(params.getAll("group").filter(Boolean))],
  };
}

export function tvQuery(settings: TvSettings, autoplay: boolean) {
  const params = new URLSearchParams({ stage: settings.stage, interval: String(settings.interval) });
  if (settings.groups === null) params.set("groups", "all");
  else if (!settings.groups.length) params.append("group", "");
  else settings.groups.forEach(group => params.append("group", group));
  if (settings.teams) params.set("teams", "1");
  if (autoplay) params.set("autoplay", "1");
  return params.toString();
}

export function paginateTv(count: number, capacity = 20, columns = 2): TvScreen[] {
  if (!count) return [];
  if (count <= capacity) return [{ left: [0, count] }];
  const screens: TvScreen[] = [];
  for (let index = 0; index < count; index += capacity * columns) {
    screens.push({ left: [index, Math.min(index + capacity, count)], ...(columns === 2 ? {
      right: [Math.min(index + capacity, count), Math.min(index + capacity * 2, count)] as [number, number],
    } : {}) });
  }
  return screens;
}

export function nextTvGroup(groups: TvGroup[], current?: string) {
  const index = groups.findIndex(group => group.slug === current);
  return groups[(index + 1) % groups.length];
}
