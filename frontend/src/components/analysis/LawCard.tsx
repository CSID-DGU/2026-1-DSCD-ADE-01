"use client";

import { useState } from "react";
import type { LawItem } from "@/types/contract";
import { TextDetailModal } from "@/components/analysis/TextDetailModal";
import { AlertTriangle } from "lucide-react";

type LawCardProps = {
  law: LawItem;
  index: number;
};

export function LawCard({ law, index }: LawCardProps) {
  const [reasonOpen, setReasonOpen] = useState(false);
  const [fullOpen, setFullOpen] = useState(false);

  const applicationReason = law.applicationReason?.trim();
  const violationStatus = law.violationStatus || law.warning?.level || "문제없음";
  const violationReason = law.violationReason || law.warning?.reason;
  const isSafeStatus = violationStatus === "안전" || violationStatus === "문제없음";
  const showStatusBox = !isSafeStatus;
  const showViolationReason = showStatusBox && Boolean(violationReason);
  const statusClassMap: Record<string, string> = {
    안전: "border-emerald-300/80 bg-emerald-50 text-emerald-950",
    문제없음: "border-emerald-300/80 bg-emerald-50 text-emerald-950",
    주의: "border-amber-400/70 bg-amber-50 text-amber-950",
    위법가능: "border-warning-border bg-warning-bg text-warning-text",
    위법소지높음: "border-warning-border bg-warning-bg text-warning-text",
  };
  const statusClass = statusClassMap[violationStatus] ?? statusClassMap["주의"];
  const fullBody =
    law.fullText?.trim() ||
    "임시 법령 원문 데이터입니다. 실제 서비스에서는 법령 API 또는 RAG 검색 결과가 연결됩니다.";

  return (
    <>
      <article className="rounded-lg border border-border-default bg-white p-3.5 shadow-sm">
        <div className="flex items-start gap-2.5">
          <span className="flex h-7 min-w-[1.75rem] shrink-0 items-center justify-center rounded-sm bg-[#D6E3FF] px-1.5 text-xs font-bold text-primary-navy">
            {index}
          </span>
          <div className="min-w-0 flex-1">
            <h4 className="text-sm font-semibold leading-snug text-text-primary">
              {law.title} {law.article || ""}
            </h4>
            <p className="mt-1.5 whitespace-pre-wrap text-sm leading-relaxed text-text-secondary">
              {law.summary}
            </p>
            {showStatusBox ? (
              <aside className={`mt-3 rounded-lg border px-3 py-2.5 text-sm shadow-sm ${statusClass}`}>
                <p className="flex items-center gap-1.5 font-semibold">
                  <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden />
                  <span>[{violationStatus}]</span>
                </p>
                {showViolationReason ? (
                  <p className="mt-1.5 whitespace-pre-wrap leading-relaxed opacity-95">
                    사유: {violationReason}
                  </p>
                ) : null}
              </aside>
            ) : null}

            {reasonOpen ? (
              <p className="mt-2 whitespace-pre-wrap rounded-md border border-border-default bg-panel-bg px-3 py-2 text-sm leading-relaxed text-text-secondary">
                {applicationReason ||
                  "등록된 적용 이유가 없습니다. 요약 문구를 참고하거나 추후 분석 결과가 연결됩니다."}
              </p>
            ) : null}

            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setFullOpen(true)}
                className="rounded-md border border-border-default bg-panel-bg px-2.5 py-1 text-xs font-medium text-text-primary transition hover:bg-page-bg"
              >
                법령 원문 보기
              </button>
              <button
                type="button"
                onClick={() => setReasonOpen((v) => !v)}
                className="rounded-md border border-border-default bg-panel-bg px-2.5 py-1 text-xs font-medium text-text-primary transition hover:bg-page-bg"
              >
                법령 관련 사유
              </button>
            </div>
          </div>
        </div>
      </article>

      <TextDetailModal
        open={fullOpen}
        onClose={() => setFullOpen(false)}
        title={`${law.title} ${law.article || ""} 원문`}
        body={fullBody}
      />
    </>
  );
}
