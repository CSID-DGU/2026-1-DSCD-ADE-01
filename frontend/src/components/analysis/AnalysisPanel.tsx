import type { ReactNode } from "react";
import type { Clause } from "@/types/contract";
import { LawCard } from "@/components/analysis/LawCard";
import { PrecedentCard } from "@/components/analysis/PrecedentCard";
import { GuideChecklist } from "@/components/analysis/GuideChecklist";
import { BottomActionBar } from "@/components/analysis/BottomActionBar";
import { extractClauseFields } from "@/lib/clauseStructuring";

type AnalysisPanelProps = {
  clause: Clause | null;
};

function EmptyHint({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-lg border border-border-default bg-white p-3.5 text-sm leading-relaxed text-text-secondary shadow-sm">
      {children}
    </div>
  );
}

export function AnalysisPanel({ clause }: AnalysisPanelProps) {
  if (!clause) {
    return (
      <div className="flex h-full max-h-full min-h-0 flex-1 flex-col items-center justify-center border border-dashed border-border-default bg-panel-bg p-8 text-center">
        <p className="text-sm text-text-secondary">좌측에서 조항을 선택해 주세요.</p>
      </div>
    );
  }

  const { analysis } = clause;
  const clauseLabel = `${clause.label}${clause.title?.trim() ? ` ${clause.title.trim()}` : ""}`;
  const structuredFields = extractClauseFields(clause.body);

  return (
    <div className="flex h-full max-h-full min-h-0 w-full min-w-0 flex-col bg-panel-bg/90">
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-3 pb-3 pt-2.5 sm:px-6">
        <section className="space-y-2 border-b border-border-default pb-3">
          <h3 className="text-[15px] font-bold text-text-primary">선택 조항 요약</h3>
          <p className="text-sm font-semibold leading-relaxed text-text-primary">{clauseLabel}</p>
          {structuredFields.length > 0 ? (
            <div className="rounded-lg border border-border-default bg-white p-3 shadow-sm">
              <p className="text-xs font-semibold text-text-secondary">핵심 항목</p>
              <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1.5">
                {structuredFields.map((f) => (
                  <div key={f.label} className="min-w-0">
                    <dt className="text-[11px] text-text-secondary">{f.label}</dt>
                    <dd className="truncate text-sm font-semibold text-text-primary">{f.value}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ) : null}
          <p className="whitespace-pre-wrap text-sm leading-[1.65] text-text-primary">{clause.body}</p>
        </section>

        <section className="space-y-2">
          <h3 className="text-[15px] font-bold text-text-primary">관련 법령</h3>
          {analysis.relatedLaws.length > 0 ? (
            <div className="flex flex-col gap-2">
              {analysis.relatedLaws.map((law, i) => (
                <LawCard key={law.id} law={law} index={i + 1} />
              ))}
            </div>
          ) : (
            <EmptyHint>관련 법령이 충분히 검색되지 않았습니다.</EmptyHint>
          )}
        </section>

        <section className="space-y-2">
          <h3 className="text-[15px] font-bold text-text-primary">관련 판례</h3>
          {analysis.precedents.length > 0 ? (
            <div className="flex flex-col gap-2.5">
              {analysis.precedents.map((p) => (
                <PrecedentCard
                  key={p.id}
                  item={p}
                  clauseId={clause.id}
                  clauseLabel={clauseLabel}
                  clauseSourcePath={clause.sourcePath}
                />
              ))}
            </div>
          ) : (
            <EmptyHint>관련 판례가 충분히 검색되지 않았습니다.</EmptyHint>
          )}
        </section>

        <section className="space-y-2">
          <h3 className="text-[15px] font-bold text-text-primary">보완 가이드</h3>
          <p className="text-[11px] leading-relaxed text-text-secondary">
            조항 기준 최종 확인·보완 사항입니다. (판례 카드 안의 「판례 기반 보완 가이드」와 구분됩니다.)
          </p>
          {analysis.supplementGuide.length > 0 ? (
            <GuideChecklist
              items={analysis.supplementGuide}
              showCardHeading={false}
              clauseId={clause.id}
              clauseLabel={clauseLabel}
              clauseSourcePath={clause.sourcePath}
            />
          ) : (
            <EmptyHint>현재 조항에 대한 보완 가이드가 없습니다.</EmptyHint>
          )}
        </section>

        <section className="space-y-2 pb-1">
          <h3 className="text-[15px] font-bold text-text-primary">수정 제안 · 챗봇</h3>
          <EmptyHint>
            AI 수정 문안·분쟁 예방 초안은 하단 버튼의 챗봇 또는 추후 기능으로 연결됩니다. (데모)
          </EmptyHint>
        </section>
      </div>

      <BottomActionBar />
    </div>
  );
}
