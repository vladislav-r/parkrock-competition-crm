"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { X } from "lucide-react";
import "./participant-club-details.css";

/** Keeps the list mounted so closing a mobile card preserves its scroll position. */
export function ResponsiveDetail({ open, onClose, label, children }: { open: boolean; onClose: () => void; label: string; children: ReactNode }) {
  const [mobile, setMobile] = useState(false);
  const panel = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const query = window.matchMedia("(max-width: 760px)");
    const update = () => setMobile(query.matches);
    update(); query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (!mobile || !open) return;
    const trigger = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    panel.current?.querySelector<HTMLButtonElement>(".mobile-detail-close")?.focus();
    function keydown(event: KeyboardEvent) {
      // Existing confirmation dialogs sit above the detail card.
      if ([...document.querySelectorAll(".modal-backdrop")].some(item => !item.classList.contains("responsive-detail"))) return;
      if (event.key === "Escape") { event.preventDefault(); close.current(); }
      if (event.key !== "Tab") return;
      const items = [...(panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]') ?? [])].filter(item => item.getClientRects().length > 0);
      const first = items[0], last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    }
    document.addEventListener("keydown", keydown);
    return () => { document.body.style.overflow = overflow; document.removeEventListener("keydown", keydown); if (trigger?.isConnected) trigger.focus({ preventScroll: true }); };
  }, [mobile, open]);
  return <div className={`responsive-detail${mobile && open ? " modal-backdrop is-open" : ""}`} hidden={mobile && !open} onMouseDown={event => { if (mobile && event.target === event.currentTarget) onClose(); }}>
    <div ref={panel} className="responsive-detail-panel" role={mobile && open ? "dialog" : undefined} aria-modal={mobile && open ? true : undefined} aria-label={mobile && open ? label : undefined}>
      <button data-view-action type="button" className="mobile-detail-close" onClick={onClose} aria-label={`Закрыть: ${label}`}><X size={20}/></button>
      {children}
    </div>
  </div>;
}
