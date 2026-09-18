"use client";
import { Info } from "lucide-react";
import { useId, useState } from "react";
export function SettingHelp({ label, children }: { label: string; children: string }) {
  const id = useId();
  const [open, setOpen] = useState(false);
  return <span className="setting-help" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
    <button type="button" className="setting-help-button" data-view-action aria-label={`О параметре «${label}»`} aria-expanded={open} aria-describedby={open ? id : undefined}
      onClick={() => setOpen(true)} onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} onKeyDown={event => { if (event.key === "Escape") { event.preventDefault(); setOpen(false); } }}><Info size={16}/></button>
    {open && <span className="setting-help-text" role="tooltip" id={id}>{children}</span>}
  </span>;
}
