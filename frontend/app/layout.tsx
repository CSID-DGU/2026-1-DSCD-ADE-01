import type { Metadata } from "next";
import { Alexandria, Public_Sans } from "next/font/google";
import "./globals.css";

const alexandria = Alexandria({
  variable: "--font-alexandria",
  subsets: ["latin"],
  weight: ["400", "500", "700"],
});

const publicSans = Public_Sans({
  variable: "--font-public-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: "ADE - 임대차 계약서 AI 분석",
  description: "임대차 계약서를 업로드하면 AI가 조항을 분석하고 위험을 검토합니다.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko" className={`${alexandria.variable} ${publicSans.variable} h-full`}>
      <body className="min-h-full">{children}</body>
    </html>
  );
}
