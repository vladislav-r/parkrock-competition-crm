import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Судейство — ПаркРок",
  description: "Рабочее место судьи ПаркРок — Управление соревнованиями",
};

export default function JudgeLayout({ children }: { children: React.ReactNode }) {
  return children;
}
