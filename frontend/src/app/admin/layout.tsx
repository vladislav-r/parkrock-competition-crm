import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "ПаркРок — Управление соревнованиями",
  description: "CRM для организации и проведения соревнований ПаркРок",
};

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return children;
}
