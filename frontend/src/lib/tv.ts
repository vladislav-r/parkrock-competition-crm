import type { Medal } from "./api";

export type TvSettings = { stage: "qualification" | "final"; interval: number; groups: string[] | null };
export type TvRow = { participant_id: string; full_name: string; club: string; place: number | null; points: number | null; medal: Medal | null; is_finalist: boolean };
export type TvGroup = { name: string; slug: string; rows: TvRow[] };
export type TvScreen = { left: [number, number]; right?: [number, number] };

export function readTvSettings(params: URLSearchParams): TvSettings {
  const interval = Number(params.get("interval"));
  return {
    stage: params.get("stage") === "final" ? "final" : "qualification",
    interval: Number.isInteger(interval) && interval >= 5 && interval <= 120 ? interval : 15,
    groups: params.get("groups") === "all" || !params.has("group") ? null : [...new Set(params.getAll("group"))],
  };
}

export function tvQuery(settings: TvSettings, autoplay: boolean) {
  const params = new URLSearchParams({ stage: settings.stage, interval: String(settings.interval) });
  if (settings.groups === null) params.set("groups", "all");
  else if (!settings.groups.length) params.append("group", "");
  else settings.groups.forEach(group => params.append("group", group));
  if (autoplay) params.set("autoplay", "1");
  return params.toString();
}

export function paginateTv(count: number): TvScreen[] {
  if (!count) return [];
  if (count <= 20) return [{ left: [0, count] }];
  const screens: TvScreen[] = [];
  for (let index = 0; index < count; index += 40) {
    screens.push({ left: [index, Math.min(index + 20, count)], right: [Math.min(index + 20, count), Math.min(index + 40, count)] });
  }
  return screens;
}

export function nextTvGroup(groups: TvGroup[], current?: string) {
  const index = groups.findIndex(group => group.slug === current);
  return groups[(index + 1) % groups.length];
}
