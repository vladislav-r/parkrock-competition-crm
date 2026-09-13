"use client";

import { useEffect } from "react";
import type { PublicResults } from "./api";

export function publicRefreshMs(data: Pick<PublicResults, "qualification_refresh_seconds" | "final_refresh_seconds"> | null, stage: string) {
  const seconds = stage === "qualification" || stage === "preparation"
    ? data?.qualification_refresh_seconds ?? 30
    : data?.final_refresh_seconds ?? 10;
  return Math.max(3, Math.min(300, seconds)) * 1000;
}

export function usePublicRefresh(load: () => Promise<void>, interval: number) {
  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const timer = window.setInterval(() => void load(), interval);
    return () => window.clearInterval(timer);
  }, [load, interval]);
}
