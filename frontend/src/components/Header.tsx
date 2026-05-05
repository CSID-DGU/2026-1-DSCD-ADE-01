"use client";

import Link from "next/link";
import { Bell, Settings, User } from "lucide-react";
import { openChatbotPanel } from "@/lib/chatbotEvents";

export type HeaderTab = "analysis" | "chatbot";

export type HeaderProps = {
  context: "upload" | "analysis";
  fileDisplayName?: string;
  /** 분석 페이지에서 상태 칩 표시 여부 (기본: analysis면 true, upload면 false) */
  showAnalysisStatus?: boolean;
  analysisStatusLabel?: string;
  /** 업로드 페이지 탭 상태 (분석 페이지에서는 시각만 고정) */
  activeTab?: HeaderTab;
  onTabChange?: (tab: HeaderTab) => void;
};

export function Header({
  context,
  fileDisplayName,
  showAnalysisStatus,
  analysisStatusLabel = "분석 완료",
  activeTab = "analysis",
  onTabChange,
}: HeaderProps) {
  const openChatbot = () => {
    openChatbotPanel();
  };

  const resolvedShowStatus =
    showAnalysisStatus ?? (context === "analysis");

  const chipText =
    context === "upload"
      ? (fileDisplayName?.trim() || "계약서를 업로드 해주세요")
      : (fileDisplayName?.trim() || "파일 미지정");

  const analysisTabSelected =
    context === "upload" ? activeTab === "analysis" : true;
  const chatbotTabSelected = context === "upload" && activeTab === "chatbot";

  const tabBase =
    "rounded-md px-3 py-1.5 text-xs transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white/60";

  const tabActive = "bg-white font-semibold text-header-navy";
  const tabInactive =
    "font-medium text-white/85 hover:bg-white/10 hover:text-white";

  const handleAnalysisTab = () => {
    if (context === "upload") {
      onTabChange?.("analysis");
    }
  };

  const handleChatbotTab = () => {
    if (context === "upload") {
      onTabChange?.("chatbot");
    } else {
      openChatbot();
    }
  };

  return (
    <header className="shrink-0 border-b border-white/10 bg-header-navy text-white">
      <div className="grid w-full grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-x-2 gap-y-2 px-4 py-3 sm:gap-x-4 sm:px-6">
        <div className="flex min-w-0 flex-wrap items-center gap-2 justify-self-start sm:gap-3">
          <Link
            href="/"
            className="truncate text-sm font-semibold tracking-tight text-white transition hover:text-white/95"
          >
            계약서 분석
          </Link>
          <span
            className="max-w-[min(100%,320px)] truncate rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs text-white/95"
            title={chipText}
          >
            {chipText}
          </span>
          {resolvedShowStatus ? (
            <span className="whitespace-nowrap rounded-md bg-success-green/25 px-2 py-0.5 text-xs font-medium text-emerald-100">
              {analysisStatusLabel}
            </span>
          ) : null}
        </div>

        <div className="inline-flex shrink-0 justify-self-center rounded-lg bg-white/10 p-0.5">
          <button
            type="button"
            className={`${tabBase} ${analysisTabSelected ? tabActive : tabInactive}`}
            onClick={handleAnalysisTab}
            aria-pressed={analysisTabSelected}
          >
            계약서 분석
          </button>
          <button
            type="button"
            className={`${tabBase} ${chatbotTabSelected ? tabActive : tabInactive}`}
            onClick={handleChatbotTab}
            aria-pressed={chatbotTabSelected}
          >
            AI 챗봇
          </button>
        </div>

        <div className="flex items-center gap-1 justify-self-end border-l border-white/0 pl-0 sm:border-white/15 sm:pl-3">
          <button
            type="button"
            className="rounded-md p-2 text-white/80 transition hover:bg-white/10 hover:text-white"
            aria-label="알림"
          >
            <Bell className="h-5 w-5" />
          </button>
          <button
            type="button"
            className="rounded-md p-2 text-white/80 transition hover:bg-white/10 hover:text-white"
            aria-label="설정"
          >
            <Settings className="h-5 w-5" />
          </button>
          <button
            type="button"
            className="rounded-md p-2 text-white/80 transition hover:bg-white/10 hover:text-white"
            aria-label="프로필"
          >
            <User className="h-5 w-5" />
          </button>
        </div>
      </div>
    </header>
  );
}
