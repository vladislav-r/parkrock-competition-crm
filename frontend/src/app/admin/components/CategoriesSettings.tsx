"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Medal, Plus, RotateCcw, Save, Trash2 } from "lucide-react";
import { AgeCategory, CategoryPreview, getAgeCategories, previewAgeCategories, updateAgeCategories } from "@/lib/api";
import { ConfirmDialog } from "./ConfirmDialog";
import { RouteToast, type RouteNotification } from "./RoutesSection";

const EMPTY_MEDALS = { bronze_min_points: null, bronze_max_points: null, silver_min_points: null, silver_max_points: null, gold_min_points: null, gold_max_points: null };
const numberValue = (value: string) => value === "" ? null : Number(value);

function sortedCategories(rows: AgeCategory[]) {
  return [...rows].sort((left, right) => left.min_age - right.min_age || (left.sex === "male" ? -1 : 1));
}

export function CategoriesSettings({ token, locked, onChanged }: { token: string; locked: boolean; onChanged: () => Promise<void> }) {
  const [categories, setCategories] = useState<AgeCategory[]>([]);
  const [preview, setPreview] = useState<CategoryPreview | null>(null);
  const [pendingPayload, setPendingPayload] = useState<AgeCategory[]>([]);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<RouteNotification | null>(null);

  const load = useCallback(async () => {
    try { setCategories((await getAgeCategories(token)).categories); }
    catch (error) { setNotice({ type: "error", title: error instanceof Error ? error.message : "Не удалось загрузить категории" }); }
  }, [token]);
  useEffect(() => { void load(); }, [load]);
  const totalParticipants = useMemo(() => categories.reduce((sum, item) => sum + (item.participant_count ?? 0), 0), [categories]);

  function update(index: number, patch: Partial<AgeCategory>) { setCategories((rows) => rows.map((item, rowIndex) => rowIndex === index ? { ...item, ...patch } : item)); }
  function add(sex: "male" | "female") {
    setCategories((rows) => [...rows, { name: "Новая категория", sex, min_age: 7, max_age: 9, finalist_count: 10, ...EMPTY_MEDALS }]);
  }
  async function requestSave() {
    setSaving(true);
    try {
      const payload = sortedCategories(categories).map(({ participant_count: _, ...item }) => item);
      const forecast = await previewAgeCategories(token, payload);
      setPendingPayload(payload); setPreview(forecast);
    } catch (error) { setNotice({ type: "error", title: error instanceof Error ? error.message : "Конфигурация некорректна" }); }
    finally { setSaving(false); }
  }
  async function save() {
    if (!preview) return;
    setSaving(true);
    try {
      const result = await updateAgeCategories(token, pendingPayload);
      setPreview(null); await load(); await onChanged();
      setNotice({ type: "success", title: `Сохранено категорий: ${result.updated}`, details: `Перераспределено участников: ${result.affected_participants}` });
    } catch (error) { setNotice({ type: "error", title: error instanceof Error ? error.message : "Не удалось сохранить категории" }); setPreview(null); }
    finally { setSaving(false); }
  }

  return <div className="category-settings">
    <div className="settings-card-head category-settings-head"><div><h2>Возрастные категории и медали</h2><p>{categories.length} категорий · {totalParticipants} участников</p></div><div><button className="secondary-button" disabled={locked} onClick={() => add("male")}><Plus size={15}/>Мужская</button><button className="secondary-button" disabled={locked} onClick={() => add("female")}><Plus size={15}/>Женская</button><button className="secondary-button" onClick={() => void load()}><RotateCcw size={15}/>Сбросить</button><button className="save-route-button" disabled={locked || saving} onClick={() => void requestSave()}><Save size={16}/>{saving ? "Проверяем..." : "Проверить и сохранить"}</button></div></div>
    {locked && <div className="category-lock-note">После запуска финала категории и медальные диапазоны заблокированы.</div>}
    <div className="category-help"><Medal size={19}/><span><strong>Финалисты и медали</strong><small>Ноль финалистов означает, что категория не участвует в финале, но её квалификацию всё равно нужно подтвердить. Пустая нижняя граница отключает медаль, пустая верхняя означает «и выше».</small></span></div>
      <div className="category-config-table"><div className="category-config-head"><span>Категория</span><span>Пол</span><span>Возраст</span><span>В финал</span><span className="bronze-label">Бронза</span><span className="silver-label">Серебро</span><span className="gold-label">Золото</span><span/></div>{categories.map((item, index) => <div className="category-config-row" key={item.id ?? `new-${index}`}><label><input value={item.name} disabled={locked} onChange={(event) => update(index, { name: event.target.value })}/><small>{item.participant_count ?? 0} участников</small></label><select value={item.sex} disabled={locked} onChange={(event) => update(index, { sex: event.target.value as "male" | "female" })}><option value="male">Мужской</option><option value="female">Женский</option></select><div className="range-inputs age-range"><input type="number" min="0" max="120" value={item.min_age} disabled={locked} onChange={(event) => update(index, { min_age: Number(event.target.value) })}/><span>—</span><input type="number" min="0" max="120" value={item.max_age ?? ""} placeholder="∞" disabled={locked} onChange={(event) => update(index, { max_age: numberValue(event.target.value) })}/></div><input className="finalist-count-input" type="number" min="0" max="1000" value={item.finalist_count} disabled={locked} title="Ноль отключает финал для категории; равенство очков на границе увеличивает положительный лимит" onChange={(event) => update(index, { finalist_count: Number(event.target.value) })}/>{(["bronze", "silver", "gold"] as const).map((medal) => <div className="range-inputs" key={medal}><input type="number" min="0" value={item[`${medal}_min_points`] ?? ""} placeholder="от" disabled={locked} onChange={(event) => update(index, { [`${medal}_min_points`]: numberValue(event.target.value) })}/><span>—</span><input type="number" min="0" value={item[`${medal}_max_points`] ?? ""} placeholder="∞" disabled={locked} onChange={(event) => update(index, { [`${medal}_max_points`]: numberValue(event.target.value) })}/></div>)}<button className="icon-button category-delete" title="Удалить категорию" disabled={locked || categories.length <= 2} onClick={() => setCategories((rows) => rows.filter((_, rowIndex) => rowIndex !== index))}><Trash2 size={15}/></button></div>)}</div>
    {preview && <ConfirmDialog title="Сохранить категории и медальные диапазоны?" description={`Будет перераспределено участников: ${preview.affected_participants} из ${preview.participant_count}. Без категории останется: ${preview.unassigned_participants}.`} confirmLabel="Применить пересчёт" busy={saving} onCancel={() => setPreview(null)} onConfirm={() => void save()}><div className="category-preview"><strong>Прогноз распределения</strong><div>{Object.entries(preview.assignments).map(([name, count]) => <span key={name}><b>{name}</b><small>{count}</small></span>)}</div>{preview.transitions.length > 0 && <><strong>Изменения</strong><ul>{preview.transitions.slice(0, 8).map((item) => <li key={`${item.from}-${item.to}`}>{item.from} → {item.to}: {item.count}</li>)}</ul></>}</div></ConfirmDialog>}
    {notice && <RouteToast notification={notice} onClose={() => setNotice(null)}/>} 
  </div>;
}
