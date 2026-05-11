"use client";

import { useState } from "react";
import type { PrecedentItem } from "@/types/contract";
import { Gavel } from "lucide-react";
import { AnalysisInfoBox } from "@/components/analysis/AnalysisInfoBox";
import { TextDetailModal } from "@/components/analysis/TextDetailModal";
import { openChatbotPanel } from "@/lib/chatbotEvents";

type PrecedentCardProps = {
  item: PrecedentItem;
  clauseId: string;
  clauseLabel: string;
  clauseSourcePath: string;
};

export function PrecedentCard({ item, clauseId, clauseLabel, clauseSourcePath }: PrecedentCardProps) {
  const heading = item.title?.trim() || "판례";
  const [originalOpen, setOriginalOpen] = useState(false);
  const courtAndCase = [item.court?.trim(), item.caseNumber?.trim()].filter(Boolean).join(".");

  const originalBody =
    item.originalText?.trim() ||
    "이 판례는 원상복구 범위와 통상 마모의 구분 기준에 대해 판단한 사례입니다. (데모용 임시 원문입니다.)";

  const askAboutPrecedent = () => {
    openChatbotPanel({
      initialMessage: "이 판례가 현재 선택한 조항에 어떤 영향을 주는지 설명해줘.",
      context: {
        clauseId,
        clauseLabel,
        clauseSourcePath,
        source: "precedent",
      },
    });
  };

  return (
    <>
      <article className="rounded-lg border border-border-default bg-white p-3.5 shadow-sm">
        <div className="flex items-start gap-2">
          <Gavel className="mt-0.5 h-4 w-4 shrink-0 text-text-secondary" aria-hidden />
          <div className="min-w-0 flex-1">
            <h4 className="text-sm font-semibold leading-snug text-text-primary">{heading}</h4>
            <p className="mt-1 text-xs font-medium text-text-secondary">
              {courtAndCase || "법원/사건번호 정보 없음"}
            </p>
            <p className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-text-primary">
              {item.summary}
            </p>
            {item.implication ? (
              <p className="mt-2 text-sm text-text-secondary">{item.implication}</p>
            ) : null}

            <div className="mt-3 space-y-2.5">
              <AnalysisInfoBox title="핵심 충돌">{item.conflictSummary?.trim() || "—"}</AnalysisInfoBox>
              <AnalysisInfoBox title="결과">{item.outcomeSummary?.trim() || "—"}</AnalysisInfoBox>
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setOriginalOpen(true)}
                className="rounded-md border border-border-default bg-panel-bg px-2.5 py-1 text-xs font-medium text-text-primary transition hover:bg-page-bg"
              >
                판례 원문 보기
              </button>
              <button
                type="button"
                onClick={askAboutPrecedent}
                className="rounded-md border border-border-default bg-panel-bg px-2.5 py-1 text-xs font-medium text-text-primary transition hover:bg-page-bg"
              >
                챗봇에게 이 판례 질문하기
              </button>
            </div>
          </div>
        </div>
      </article>

      <TextDetailModal
        open={originalOpen}
        onClose={() => setOriginalOpen(false)}
        title={`${heading} — 판례 원문`}
        body={originalBody}
      />
    </>
  );
}
