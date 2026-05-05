import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "임대차 계약서 AI 분석",
  description: "계약서 업로드 및 AI 분석",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ko">
      <body className="font-pretendard antialiased">{children}</body>
    </html>
  );
}
