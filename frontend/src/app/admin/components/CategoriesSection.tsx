"use client";

import type { EventInfo } from "@/lib/api";
import { CategoriesSettings } from "./CategoriesSettings";

export function CategoriesSection({ token, event, onChanged }: { token: string; event: EventInfo | null; onChanged: () => Promise<void> }) {
  return <section className="categories-pane"><div className="admin-workspace-container">
    <header className="admin-section-hero"><div><div className="eyebrow">Конфигурация фестиваля</div><h1>Категории и медали</h1><p>Возрастные группы, количество финалистов и диапазоны награждения.</p></div></header>
    <CategoriesSettings token={token} locked={Boolean(event?.final_started_at)} onChanged={onChanged}/>
  </div></section>;
}
