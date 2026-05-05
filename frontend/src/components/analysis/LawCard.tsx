"use client";

import { useState } from "react";
import type { LawItem } from "@/types/contract";
import { LawWarningBox } from "@/components/analysis/LawWarningBox";
import { TextDetailModal } from "@/components/analysis/TextDetailModal";

type LawCardProps = {
  law: LawItem;
  index: number;
};

export function LawCard({ law, index }: LawCardProps) {
  const [reasonOpen, setReasonOpen] = useState(false);
  const [violationOpen, setViolationOpen] = useState(false);
  const [fullOpen, setFullOpen] = useState(false);

  const hasWarning = Boolean(law.warning);
  const applicationReason = law.applicationReason?.trim();
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
              {law.title} {law.article}
            </h4>
            <p className="mt-1.5 whitespace-pre-wrap text-sm leading-relaxed text-text-secondary">
              {law.summary}
            </p>
            {law.warning ? <LawWarningBox warning={law.warning} /> : null}

            {reasonOpen ? (
              <p className="mt-2 whitespace-pre-wrap rounded-md border border-border-default bg-panel-bg px-3 py-2 text-sm leading-relaxed text-text-secondary">
                {applicationReason ||
                  "등록된 적용 이유가 없습니다. 요약 문구를 참고하거나 추후 분석 결과가 연결됩니다."}
              </p>
            ) : null}

            {hasWarning && violationOpen ? (
              <p className="mt-2 whitespace-pre-wrap rounded-md border border-warning-border/40 bg-warning-bg/80 px-3 py-2 text-sm leading-relaxed text-warning-text">
                {law.warning?.detail?.trim() ||
                  law.warning?.reason ||
                  "세부 위반 사유가 별도로 등록되지 않았습니다."}
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
                조항 적용 이유 보기
              </button>
              {hasWarning ? (
                <button
                  type="button"
                  onClick={() => setViolationOpen((v) => !v)}
                  className="rounded-md border border-border-default bg-panel-bg px-2.5 py-1 text-xs font-medium text-text-primary transition hover:bg-page-bg"
                >
                  위반 사유 펼치기
                </button>
              ) : null}
            </div>
          </div>
        </div>
      </article>

      <TextDetailModal
        open={fullOpen}
        onClose={() => setFullOpen(false)}
        title={`${law.title} ${law.article} 원문`}
        body={fullBody}
      />
    </>
  );
}
