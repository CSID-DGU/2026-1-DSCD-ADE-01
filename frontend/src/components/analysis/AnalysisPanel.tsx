import { useEffect, useState, type ReactNode } from "react";
import type { Clause, ContractChecklistItem } from "@/types/contract";
import { LawCard } from "@/components/analysis/LawCard";
import { PrecedentCard } from "@/components/analysis/PrecedentCard";
import { BottomActionBar } from "@/components/analysis/BottomActionBar";

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

function cloneChecklist(items: ContractChecklistItem[]): ContractChecklistItem[] {
  return items.map((item) => ({ ...item, checked: item.checked ?? false }));
}

export function AnalysisPanel({ clause }: AnalysisPanelProps) {
  const [checklist, setChecklist] = useState<ContractChecklistItem[]>([]);

  useEffect(() => {
    setChecklist(cloneChecklist(clause?.analysis.contractChecklist ?? []));
  }, [clause?.id, clause?.sourcePath, clause?.analysis.contractChecklist]);

  if (!clause) {
    return (
      <div className="flex h-full max-h-full min-h-0 flex-1 flex-col items-center justify-center border border-dashed border-border-default bg-panel-bg p-8 text-center">
        <p className="text-sm text-text-secondary">좌측에서 조항을 선택해 주세요.</p>
      </div>
    );
  }

  const { analysis } = clause;
  const clauseLabel = `${clause.label}${clause.title?.trim() ? ` ${clause.title.trim()}` : ""}`;
  const clauseText = analysis.clauseText?.trim() || clause.body;

  return (
    <div className="flex h-full max-h-full min-h-0 w-full min-w-0 flex-col bg-panel-bg/90">
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-3 pb-3 pt-2.5 sm:px-6">
        <section className="space-y-2 border-b border-border-default pb-3">
          <h3 className="text-[15px] font-bold text-text-primary">선택 조항 원문</h3>
          <p className="text-sm font-semibold leading-relaxed text-text-primary">{clauseLabel}</p>
          <p className="whitespace-pre-wrap text-sm leading-[1.65] text-text-primary">{clauseText}</p>
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
          <h3 className="text-[15px] font-bold text-text-primary">계약서 내 특약 간 관계성</h3>
          {(analysis.relatedClauses?.length ?? 0) > 0 ? (
            <div className="space-y-2">
              {analysis.relatedClauses?.map((item) => (
                <article
                  key={`${clause.id}-${item.clauseId}`}
                  className="rounded-lg border border-border-default bg-white p-3.5 shadow-sm"
                >
                  <p className="text-sm font-semibold text-text-primary">{item.clauseId}</p>
                  <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-text-primary">
                    {item.clauseText}
                  </p>
                  <p className="mt-2 rounded-md border border-border-default bg-panel-bg px-3 py-2 text-sm leading-relaxed text-text-secondary">
                    {item.relation}
                  </p>
                </article>
              ))}
            </div>
          ) : (
            <EmptyHint>연결된 특약 관계 데이터가 없습니다.</EmptyHint>
          )}
        </section>

        <section className="space-y-2 pb-1">
          <h3 className="text-[15px] font-bold text-text-primary">계약서 체크리스트</h3>
          {checklist.length > 0 ? (
            <section className="rounded-lg border border-guide-border bg-guide-bg p-3.5">
              <ul className="space-y-2 text-sm leading-relaxed text-text-secondary">
                {checklist.map((item) => (
                  <li key={item.id} className="flex gap-2">
                    <button
                      type="button"
                      role="checkbox"
                      aria-checked={Boolean(item.checked)}
                      onClick={() =>
                        setChecklist((prev) =>
                          prev.map((x) => (x.id === item.id ? { ...x, checked: !x.checked } : x)),
                        )
                      }
                      className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border border-border-default text-[10px] font-bold leading-none transition ${
                        item.checked
                          ? "border-primary-navy bg-primary-navy text-white"
                          : "bg-white text-transparent"
                      }`}
                    >
                      ✓
                    </button>
                    <div className="min-w-0">
                      <p className="font-semibold text-text-primary">{item.item}</p>
                      <p className="mt-1 whitespace-pre-wrap">{item.description}</p>
                      <p className="mt-1 text-xs text-text-secondary">근거: {item.basis}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ) : (
            <EmptyHint>확인할 체크리스트 항목이 없습니다.</EmptyHint>
          )}
        </section>
      </div>

      <BottomActionBar />
    </div>
  );
}
