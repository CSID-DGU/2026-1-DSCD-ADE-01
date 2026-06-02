"use client";

import { useEffect, useState } from "react";
import { TopNavBar } from "@/components/TopNavBar";
import { DocumentPanel } from "@/components/analysis/DocumentPanel";
import { LawSection } from "@/components/analysis/LawSection";
import { PrecedentSection } from "@/components/analysis/PrecedentSection";
import { BottomActionBar } from "@/components/analysis/BottomActionBar";
import type { LawItem } from "@/components/analysis/LawSection";
import type { PrecedentItem } from "@/components/analysis/PrecedentSection";
import { Loader2, AlertCircle } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

type ClauseResult = {
  laws: LawItem[];
  precedents: PrecedentItem[];
  status: "loading" | "done" | "error";
};

/* ─── Page ─────────────────────────────────────────────────────────── */

export default function AnalysisPage() {
  const [fileName, setFileName] = useState<string>("계약서 분석 중...");
  const [generalTerms, setGeneralTerms] = useState<{title: string, text: string}[]>([]);
  const [specialTerms, setSpecialTerms] = useState<string[]>([]);
  const [clauseResults, setClauseResults] = useState<Record<number, ClauseResult>>({});
  const [analysisStatus, setAnalysisStatus] = useState<"loading" | "done">("loading");
  const [completedCount, setCompletedCount] = useState(0);

  useEffect(() => {
    const storedFileName = sessionStorage.getItem("ade.analysis.fileName");
    const storedDocId = sessionStorage.getItem("ade.analysis.docId");
    const storedContract = sessionStorage.getItem("ade.analysis.contract");
    const clientId = localStorage.getItem("ade.client_id");

    if (storedFileName) setFileName(storedFileName);
    
    if (storedContract && storedDocId && clientId) {
      try {
        const contract = JSON.parse(storedContract);
        
        // 1. 일반 조항 추출
        const gTerms = [];
        if (contract.general_terms) {
          for (let i = 1; i <= 13; i++) {
            const artKey = `art${i}`;
            if (contract.general_terms[artKey] && contract.general_terms[artKey].text) {
              gTerms.push({
                title: `제 ${i} 조`,
                text: contract.general_terms[artKey].text
              });
            }
          }
        }
        setGeneralTerms(gTerms);

        // 2. 분석할 특약 필터링 및 초기 상태 설정
        const terms = contract.special_terms.filter((t: string) => t.trim().length > 0);
        setSpecialTerms(terms);

        const initialResults: Record<number, ClauseResult> = {};
        terms.forEach((_: string, i: number) => {
          initialResults[i] = { laws: [], precedents: [], status: "loading" };
        });
        setClauseResults(initialResults);

        if (terms.length === 0) {
          setAnalysisStatus("done");
          return;
        }

        // 3. 병렬 분석 실행
        terms.forEach(async (termText: string, index: number) => {
          try {
            const res = await fetch(`${API_BASE}/api/analyze/clause`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                client_id: clientId,
                doc_id: storedDocId,
                clause_index: index,
                clause_text: termText
              }),
            });

            if (res.ok) {
              const data = await res.json();
              const termLaws: LawItem[] = [];
              const termPrecedents: PrecedentItem[] = [];

              data.top_results.forEach((doc: any) => {
                if (doc.source_type === "law") {
                  termLaws.push({
                    rank: termLaws.length + 1,
                    name: doc.title,
                    detail: doc.content
                  });
                } else if (doc.source_type === "precedent") {
                  termPrecedents.push({
                    title: doc.title,
                    tags: ["#관련판례"],
                    facts: [{ label: "판결 요지", text: doc.content }],
                    guide: []
                  });
                }
              });

              setClauseResults(prev => ({
                ...prev,
                [index]: { laws: termLaws, precedents: termPrecedents, status: "done" }
              }));
            } else {
              setClauseResults(prev => ({ ...prev, [index]: { ...prev[index], status: "error" } }));
            }
          } catch (err) {
            console.error(`특약 ${index} 분석 에러:`, err);
            setClauseResults(prev => ({ ...prev, [index]: { ...prev[index], status: "error" } }));
          } finally {
            setCompletedCount(prev => {
              const next = prev + 1;
              if (next === terms.length) setAnalysisStatus("done");
              return next;
            });
          }
        });

      } catch (e) {
        console.error("데이터 파싱 오류", e);
        setAnalysisStatus("done");
      }
    } else {
      setAnalysisStatus("done");
    }
  }, []);

  const handleTermClick = (index: number) => {
    const element = document.getElementById(`analysis-result-${index}`);
    if (element) {
      element.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <div className="flex flex-col h-screen overflow-hidden" style={{ background: "#F4F3F7" }}>
      <TopNavBar
        mode="analysis"
        fileName={`${fileName} ${specialTerms.length > 0 && analysisStatus === "loading" ? `(분석 중: ${completedCount}/${specialTerms.length})` : ""}`}
        analysisStatus={analysisStatus}
        activeTab="analysis"
      />

      <div className="flex flex-row flex-1 min-h-0">
        <DocumentPanel 
          specialTerms={specialTerms}
          generalTerms={generalTerms}
          onTermClick={handleTermClick}
        />

        <section
          className="flex flex-col flex-1 overflow-y-auto px-8 py-8 gap-8"
          style={{ background: "#FAF9FD", paddingBottom: "128px" }}
        >
          {specialTerms.length > 0 ? (
            specialTerms.map((term, idx) => (
              <div 
                key={idx} 
                id={`analysis-result-${idx}`}
                className="flex flex-col gap-6 p-6 rounded-xl border bg-white shadow-sm scroll-mt-4"
                style={{ borderColor: "#E2E8F0" }}
              >
                {/* 특약 헤더 */}
                <div className="flex items-start justify-between gap-4">
                  <div className="flex flex-col gap-1">
                    <span className="text-xs font-bold text-blue-600 uppercase tracking-wider">특약 {idx + 1} 분석 결과</span>
                    <h4 className="text-base font-semibold text-gray-900 leading-relaxed">
                      "{term}"
                    </h4>
                  </div>
                  {clauseResults[idx]?.status === "loading" && (
                    <div className="flex items-center gap-2 text-sm text-blue-500 font-medium bg-blue-50 px-3 py-1.5 rounded-full">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      분석 중
                    </div>
                  )}
                  {clauseResults[idx]?.status === "error" && (
                    <div className="flex items-center gap-2 text-sm text-red-500 font-medium bg-red-50 px-3 py-1.5 rounded-full">
                      <AlertCircle className="h-4 w-4" />
                      분석 실패
                    </div>
                  )}
                </div>

                {/* 분석 결과 (로딩 완료 시에만) */}
                {clauseResults[idx]?.status !== "loading" && (
                  <div className="flex flex-col gap-8 pt-4 border-t border-gray-100">
                    {clauseResults[idx].laws.length > 0 ? (
                      <LawSection laws={clauseResults[idx].laws} />
                    ) : (
                      <p className="text-sm text-gray-400 italic">관련 법령을 찾지 못했습니다.</p>
                    )}
                    
                    {clauseResults[idx].precedents.length > 0 && (
                      <PrecedentSection precedents={clauseResults[idx].precedents} />
                    )}
                  </div>
                )}
              </div>
            ))
          ) : (
            <div className="flex items-center justify-center h-64 text-gray-500 border border-dashed rounded-xl">
              분석할 특약사항이 없습니다.
            </div>
          )}
        </section>
      </div>

      <BottomActionBar />
    </div>
  );
}
