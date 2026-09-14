"use client";

import { useState } from "react";
import type { EventInfo } from "@/lib/api";
import { CategoriesSettings } from "./CategoriesSettings";

export function CategoriesSection({ token, event, onChanged }: { token: string; event: EventInfo | null; onChanged: () => Promise<void> }) {
  const [summary, setSummary] = useState({ categories: 0, participants: 0 });
  return <section className="categories-pane"><div className="admin-workspace-container">
    <header className="admin-section-hero"><div><h1>Категории и медали</h1><div className="category-section-subtitle"><p>Возрастные группы, количество финалистов и диапазоны награждения.</p><span>{summary.categories} категорий · {summary.participants} участников</span></div></div></header>
    <CategoriesSettings onSummary={setSummary} token={token} locked={Boolean(event?.final_started_at)} onChanged={onChanged}/>
  </div></section>;
}
