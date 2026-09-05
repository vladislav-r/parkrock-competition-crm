"use client";

import { CheckCircle2, ShieldCheck, X } from "lucide-react";
import { UserRole } from "@/lib/api";

const ROLE_GUIDES: Record<UserRole, { title: string; intro: string; actions: string[] }> = {
  reception: {
    title: "Рабочее место ресепшена",
    intro: "Подготовьте участников к старту и поддерживайте актуальные статусы приёма.",
    actions: ["Находите участника по номеру или ФИО.", "Подтверждайте прибытие и оплату.", "До прибытия при необходимости переносите участника в другой сет."],
  },
  secretary: {
    title: "Рабочее место секретаря",
    intro: "Контролируйте данные участников и результаты на всех этапах соревнования.",
    actions: ["Во время квалификации вносите прохождения трасс.", "Проверяйте возрастные группы и подтверждайте квалификацию.", "Во время финала контролируйте таблицы и исправляйте результаты."],
  },
  chief_judge: {
    title: "Рабочее место главного судьи",
    intro: "Управляйте спортивной частью фестиваля и переходами между этапами.",
    actions: ["Проверьте квалификационные результаты по каждой группе.", "Запускайте финал только после общего подтверждения квалификации.", "Назначайте финальные трассы и контролируйте итоговые места."],
  },
  administrator: {
    title: "Рабочее место администратора",
    intro: "Вам доступны все рабочие процессы, настройки и средства восстановления данных.",
    actions: ["Контролируйте пользователей, роли и журнал действий.", "Перед переходами этапов дождитесь успешного создания резервной копии.", "Используйте восстановление и откат этапов только после проверки выбранного снимка."],
  },
  route_judge: {
    title: "Рабочее место судьи на трассе",
    intro: "Фиксируйте результат только на закреплённой за вами финальной трассе.",
    actions: ["Найдите финалиста по стартовому номеру или ФИО.", "Последовательно отмечайте попытки, зону и топ.", "Проверьте результат перед подтверждением; отправленная запись блокируется для судьи."],
  },
};

export function RoleGuideDialog({ role, onClose }: { role: UserRole; onClose: () => void }) {
  const guide = ROLE_GUIDES[role];
  return <div className="modal-backdrop role-guide-backdrop" role="presentation" onMouseDown={onClose}><section className="role-guide-dialog" role="dialog" aria-modal="true" aria-labelledby="role-guide-title" onMouseDown={(event) => event.stopPropagation()}><button className="dialog-close" onClick={onClose} title="Закрыть"><X size={18}/></button><span className="role-guide-icon"><ShieldCheck size={25}/></span><div className="eyebrow">Краткая инструкция</div><h2 id="role-guide-title">{guide.title}</h2><p>{guide.intro}</p><div className="role-guide-steps">{guide.actions.map((action) => <div key={action}><CheckCircle2 size={18}/><span>{action}</span></div>)}</div><button className="primary-action role-guide-continue" onClick={onClose}>Перейти к работе</button></section></div>;
}
