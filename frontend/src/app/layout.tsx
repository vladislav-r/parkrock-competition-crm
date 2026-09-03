import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ПаркРок: Каменный век",
  description: "Онлайн-табло фестиваля «ПаркРок: Каменный век»",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru">
      <body>{children}</body>
    </html>
  );
}
