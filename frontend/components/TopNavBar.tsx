"use client";

import { useRouter } from "next/navigation";

export type NavTab = "analysis" | "chatbot";

type TopNavBarProps = {
  fileName?: string;
  mode?: "upload" | "analysis";
  analysisStatus?: "done" | "loading";
  activeTab?: NavTab;
  onTabChange?: (tab: NavTab) => void;
};

export function TopNavBar({
  fileName,
  mode = "upload",
  analysisStatus,
  activeTab = "analysis",
  onTabChange,
}: TopNavBarProps) {
  const router = useRouter();

  const chipText =
    mode === "upload"
      ? (fileName?.trim() || "계약서를 업로드 해주세요")
      : (fileName?.trim() || "파일 미지정");

  const showStatus = mode === "analysis" && analysisStatus === "done";

  const tabBase =
    "rounded-md px-3 py-1.5 text-xs transition focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white/60";
  const tabActive = "bg-white font-semibold text-[#1E293B]";
  const tabInactive = "font-medium text-white/85 hover:bg-white/10 hover:text-white";

  return (
    <header
      className="shrink-0 border-b border-white/10"
      style={{ background: "#1E293B", color: "white" }}
    >
      <div
        className="grid w-full items-center gap-x-2 px-4 py-3 sm:gap-x-4 sm:px-6"
        style={{ gridTemplateColumns: "minmax(0,1fr) auto minmax(0,1fr)" }}
      >
        {/* Left: Logo + chip + status */}
        <div className="flex min-w-0 flex-wrap items-center gap-2 justify-self-start sm:gap-3">
          <div 
            className="flex items-center gap-2 cursor-pointer"
            onClick={() => router.push('/')}
          >
            <svg width="16" height="20" viewBox="0 0 16 20" fill="none">
              <rect width="16" height="20" rx="2" fill="white" />
              <rect x="3" y="5" width="10" height="1.5" rx="0.75" fill="#1E293B" />
              <rect x="3" y="8" width="10" height="1.5" rx="0.75" fill="#1E293B" />
              <rect x="3" y="11" width="7" height="1.5" rx="0.75" fill="#1E293B" />
            </svg>
            <span
              className="text-sm font-semibold tracking-tight text-white"
              style={{ fontFamily: "var(--font-alexandria)" }}
            >
              ADE
            </span>
          </div>

          <span
            className="max-w-[min(100%,240px)] truncate rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs text-white/95"
            title={chipText}
            style={{ fontFamily: "var(--font-alexandria)" }}
          >
            {chipText}
          </span>

          {showStatus && (
            <span
              className="whitespace-nowrap rounded-md px-2 py-0.5 text-xs font-medium text-emerald-100"
              style={{ background: "rgba(52,211,153,0.25)" }}
            >
              분석 완료
            </span>
          )}
        </div>

        {/* Center: Empty (Removed) */}
        <div />

        {/* Right: Empty (Removed) */}
        <div />
      </div>
    </header>
  );
}
