"use client";
import { useEffect } from "react";
import { ApiError, closeInvalidSession, probeConnection, reportConnection } from "./api";

export function usePresence(token: string) {
  useEffect(() => {
    if (!token) return;
    let stopped = false;
    let busy = false;
    let failedAt = 0;
    let controller: AbortController | undefined;
    let expiresAt = 0;
    try { expiresAt = Number(JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))).exp) * 1000; } catch { /* Server rejects malformed credentials. */ }
    async function heartbeat() {
      if (stopped || busy || localStorage.getItem("parkrock_admin_token") !== token) return;
      if (expiresAt && Date.now() >= expiresAt) { stopped = true; closeInvalidSession(token, "Срок сеанса истёк. Войдите снова."); return; }
      busy = true;
      controller = new AbortController();
      const timeout = window.setTimeout(() => controller?.abort(), 8000);
      try {
        const start = performance.now();
        await probeConnection(token, controller.signal);
        const latency = Math.min(60000, Math.round(performance.now() - start));
        if (!stopped) await reportConnection(token, latency, Date.now() - failedAt < 30000, controller.signal);
      } catch (error) {
        failedAt = Date.now();
        if (error instanceof ApiError && error.status === 401) stopped = true;
      } finally { window.clearTimeout(timeout); busy = false; }
    }
    const wake = () => { if (document.visibilityState === "visible") void heartbeat(); };
    void heartbeat();
    const timer = window.setInterval(() => void heartbeat(), 10000);
    const changedSession = (event: StorageEvent) => {
      if (event.key === "parkrock_admin_token" && event.newValue !== token) window.location.replace("/admin");
    };
    window.addEventListener("storage", changedSession);
    window.addEventListener("online", wake);
    document.addEventListener("visibilitychange", wake);
    return () => {
      stopped = true; controller?.abort(); window.clearInterval(timer);
      window.removeEventListener("online", wake);
      window.removeEventListener("storage", changedSession);
      document.removeEventListener("visibilitychange", wake);
    };
  }, [token]);
}
