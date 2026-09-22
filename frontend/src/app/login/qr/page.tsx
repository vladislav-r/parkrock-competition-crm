"use client";

import { useEffect, useRef, useState } from "react";
import { CrmLogo } from "../../admin/components/CrmLogo";
import { loginQr, previewQr } from "@/lib/api";
import "../../admin/relief.css";

export default function QrLoginPage() {
  const key = useRef<string | null>(null);
  const [user, setUser] = useState<{ full_name: string; qr_session_hours: number } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (key.current === null) {
      key.current = new URLSearchParams(window.location.hash.slice(1)).get("key") ?? "";
      window.history.replaceState(null, "", "/login/qr");
    }
    if (!/^[A-Za-z0-9_-]{43}$/.test(key.current)) { setError("Отсканируйте персональный QR-код ещё раз."); return; }
    let active = true;
    void previewQr(key.current).then(value => { if (active) setUser(value); }).catch(cause => {
      if (active) setError(cause instanceof Error ? cause.message : "Не удалось проверить QR-код");
    });
    return () => { active = false; };
  }, []);
  async function enter() {
    if (busy || !key.current) return;
    setBusy(true); setError("");
    try {
      const result = await loginQr(key.current);
      localStorage.setItem("parkrock_admin_token", result.access_token);
      sessionStorage.removeItem("parkrock_session_message");
      sessionStorage.setItem("parkrock_show_role_guide", "1");
      key.current = "";
      window.location.replace("/admin");
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Не удалось войти"); setBusy(false); }
  }
  return <main className="login-page"><section className="login-panel">
    <a className="back-link" href="/admin">Вход по паролю</a><CrmLogo/><h1>Вход по QR</h1>
    {user ? <><p><strong>{user.full_name}</strong><br/>Срок сеанса: {user.qr_session_hours} ч.</p>
      <p>При входе предыдущий сеанс этой учётной записи завершится.</p>
      <button className="primary-button" style={{ width: "100%" }} disabled={busy} onClick={() => void enter()}>{busy ? "Входим…" : "Войти"}</button></>
      : !error && <p role="status">Проверяем QR-код…</p>}
    {error && <p className="form-error" role="alert">{error}</p>}
  </section></main>;
}
