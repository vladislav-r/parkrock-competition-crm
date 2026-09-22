import type { Metadata } from "next";

export const metadata: Metadata = { title: "Вход по QR — ParkRock Hub", robots: { index: false, follow: false }, referrer: "no-referrer" };

export default function QrLayout({ children }: { children: React.ReactNode }) { return children; }
