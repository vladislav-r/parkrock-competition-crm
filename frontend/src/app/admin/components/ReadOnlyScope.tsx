"use client";

import { useLayoutEffect, useRef, type ReactNode, type SyntheticEvent } from "react";

// Read-only screens opt navigation/filter controls in explicitly. New actions
// are disabled by default; the backend independently rejects every mutation.
const controls = "button,input,select,textarea,[contenteditable=true],[role=switch]";
const allowed = (element: Element) => element.hasAttribute("data-view-action") || !!element.closest("form[data-view-action]");

export function ReadOnlyScope({ enabled, children }: { enabled: boolean; children: ReactNode }) {
  const root = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (!enabled || !root.current) return;
    const previous = new Map<Element, boolean>();
    const disable = () => {
      root.current?.querySelectorAll(controls).forEach(element => {
        if (allowed(element)) return;
        if (element instanceof HTMLButtonElement || element instanceof HTMLInputElement || element instanceof HTMLSelectElement || element instanceof HTMLTextAreaElement) {
          if (!previous.has(element)) previous.set(element, element.disabled);
          if (!element.disabled) element.disabled = true;
        }
      });
    };
    disable();
    const observer = new MutationObserver(disable);
    observer.observe(root.current, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled"] });
    return () => {
      observer.disconnect();
      previous.forEach((disabled, element) => { if ("disabled" in element) (element as HTMLButtonElement).disabled = disabled; });
    };
  }, [enabled]);
  function guard(event: SyntheticEvent) {
    if (!enabled || !(event.target instanceof Element)) return;
    const control = event.type === "submit" ? event.target : event.target.closest(controls);
    if (control && !allowed(control)) { event.preventDefault(); event.stopPropagation(); }
  }
  return <div ref={root} style={{ display: "contents" }} onClickCapture={guard} onChangeCapture={guard} onSubmitCapture={guard}>{children}</div>;
}
