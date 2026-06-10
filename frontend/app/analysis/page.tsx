"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { TopNavBar } from "@/components/TopNavBar";
import { DocumentPanel } from "@/components/analysis/DocumentPanel";
import { LawSection } from "@/components/analysis/LawSection";
import { PrecedentSection } from "@/components/analysis/PrecedentSection";
// import { BottomActionBar } from "@/components/analysis/BottomActionBar";
import { ChatBot } from "@/components/analysis/ChatBot";
import type { LawItem } from "@/components/analysis/LawSection";
import type { PrecedentItem } from "@/components/analysis/PrecedentSection";
import { Loader2, AlertCircle, ChevronDown, X } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

type Notification = {
  id: string;
  clauseIdx: number;
  message: string;
  isExiting?: boolean;
  timeoutId?: NodeJS.Timeout; // Add this line
};

type ClauseResult = {
  laws: LawItem[];
  precedents: PrecedentItem[];
  rawLaws: any[];
  rawPrecs: any[];
  llmRelatedLaws: RelatedLaw[];
  clauseOneLineSummary?: string;
  clauseInterpretation?: string;
  status: "loading" | "done" | "error";
};

type ChecklistItem = {
  item: string;
  description: string;
  basis: string[];
};

type RelatedLaw = {
  type: string;
  ref: string;
  summary: string;
  content: string;
  is_violation?: boolean;
  is_caution?: boolean;
};

type RelatedClause = {
  clause_id: string;
  clause_text: string;
  relation: string;
};

type FinalReportOutput = {
  contract_checklist: ChecklistItem[];
  related_clauses_map: Record<string, RelatedClause[]>;
};

/* ─── Page ─────────────────────────────────────────────────────────── */

export default function AnalysisPage() {
  const [fileName, setFileName] = useState<string>("계약서 분석 중...");
  const [generalTerms, setGeneralTerms] = useState<{title: string, text: string}[]>([]);
  const [specialTerms, setSpecialTerms] = useState<string[]>([]);
  const [clauseResults, setClauseResults] = useState<Record<number, ClauseResult>>({});
  const [analysisStatus, setAnalysisStatus] = useState<"loading" | "done">("loading");
  const [completedCount, setCompletedCount] = useState(0);
  
  const [reportData, setReportData] = useState<FinalReportOutput | null>(null);
  const [reportStatus, setReportStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [viewTab, setViewTab] = useState<"analysis" | "checklist">("analysis");

  const [openPopover, setOpenPopover] = useState<string | null>(null);
  const [activeClauseIdx, setActiveClauseIdx] = useState<number | null>(null);

  type RewriteCache = { rewrittenClause: string; reason: string };
  type RewriteModal = {
    clauseIdx: number;
    clauseText: string;
    violationLaws: RelatedLaw[];
    allRelatedLaws: RelatedLaw[];
    status: "loading" | "done" | "error";
    rewrittenClause?: string;
    reason?: string;
  };
  const [rewriteCache, setRewriteCache] = useState<Record<number, RewriteCache>>(() => {
    try {
      const raw = sessionStorage.getItem("ade.rewrite.cache");
      return raw ? JSON.parse(raw) : {};
    } catch { return {}; }
  });
  const [rewriteModal, setRewriteModal] = useState<RewriteModal | null>(null);
  const [showChecklistToast, setShowChecklistToast] = useState(false);
  const checklistTabRef = useRef<HTMLButtonElement>(null);
  const [toastPos, setToastPos] = useState<{ left: number; top: number } | null>(null);

  // 체크리스트 완료 토스트
  useEffect(() => {
    if (reportStatus === "done") {
      setShowChecklistToast(true);
    }
  }, [reportStatus]);

  useEffect(() => {
    if (showChecklistToast && checklistTabRef.current) {
      const rect = checklistTabRef.current.getBoundingClientRect();
      setToastPos({ left: rect.left + rect.width / 2, top: rect.top });
    }
  }, [showChecklistToast]);

  const clauseResultsCount = Object.keys(clauseResults).length;

  // 재작성 모달 열릴 때 배경 스크롤 차단
  useEffect(() => {
    document.body.style.overflow = rewriteModal ? "hidden" : "";
    return () => { document.body.style.overflow = ""; };
  }, [rewriteModal]);

  // 알림 관리 (최대 5개, 초과 시 순차 제거)
  useEffect(() => {
    // If the number of notifications exceeds 5 (i.e., 6 or more)
    if (notifications.length > 5) {
      const oldestNotification = notifications[0]; // Always target the very oldest
      
      // Clear its auto-dismissal timeout if it exists
      if (oldestNotification.timeoutId) {
        clearTimeout(oldestNotification.timeoutId);
      }

      // Remove the oldest notification immediately (without isExiting animation for the limit)
      setNotifications(current => current.slice(1)); // Remove the first element
    }
  }, [notifications]);

  useEffect(() => {
    const storedFileName = sessionStorage.getItem("ade.analysis.fileName");
    const storedDocId = sessionStorage.getItem("ade.analysis.docId");
    const storedContract = sessionStorage.getItem("ade.analysis.contract");
    const clientId = localStorage.getItem("ade.client_id");

    // 새 분석 시작 시 재작성 캐시 초기화
    sessionStorage.removeItem("ade.rewrite.cache");
    setRewriteCache({});

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
          initialResults[i] = { laws: [], precedents: [], rawLaws: [], rawPrecs: [], llmRelatedLaws: [], clauseInterpretation: undefined, status: "loading" };
        });
        setClauseResults(initialResults);

        if (terms.length === 0) {
          setAnalysisStatus("done");
          return;
        }

        // 3. 병렬 분석 실행 (V2: RAG + LLM 요약)
        terms.forEach(async (termText: string, index: number) => {
          // 상위 6개 공통 특약은 분석을 수행하지 않음
          if (index < 6) {
            setClauseResults(prev => ({
              ...prev,
              [index]: { ...prev[index], status: "done" }
            }));
            setCompletedCount(prev => {
              const next = prev + 1;
              if (next === terms.length) setAnalysisStatus("done");
              return next;
            });
            return;
          }

          try {
            const res = await fetch(`${API_BASE}/api/analyze/clause_v2`, {
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

              if (data && Array.isArray(data.law_results)) {
                data.law_results.forEach((doc: any) => {
                  termLaws.push({
                    rank: doc.rank ?? termLaws.length + 1,
                    name: doc.title ?? "제목 없음",
                    detail: doc.content ?? "내용 없음"
                  });
                });
              }

              if (data && Array.isArray(data.prec_results)) {
                data.prec_results.forEach((doc: any) => {
                  termPrecedents.push({
                    title: doc.title ?? "제목 없음",
                    tags: ["#관련판례"],
                    facts: [{ label: "판결 요지", text: doc.content ?? "내용 없음" }],
                    guide: []
                  });
                });
              }

              setClauseResults(prev => ({
                ...prev,
                [index]: {
                  laws: termLaws,
                  precedents: termPrecedents,
                  rawLaws: data?.law_results ?? [],
                  rawPrecs: data?.prec_results ?? [],
                  llmRelatedLaws: data?.llm_related_laws ?? [],
                  clauseOneLineSummary: data?.clause_one_line_summary ?? undefined,
                  clauseInterpretation: data?.clause_interpretation ?? undefined,
                  status: "done"
                }
              }));

              setNotifications(prev => {
                const isCommon = index < 6;
                const label = isCommon ? `공통특약 ${index + 1}` : `특약 ${index - 6 + 1}`;
                const newNotification = {
                  id: Date.now().toString() + "-" + index, // Ensure unique ID
                  clauseIdx: index,
                  message: `${label} 분석이 완료되었습니다.`,
                };
                const timeoutId = setTimeout(() => {
                  setNotifications(current => current.filter(n => n.id !== newNotification.id));
                }, 10000); // 10초 후 제거
                return [...prev, { ...newNotification, timeoutId }];
              });
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

  // 4. 모든 특약 분석 완료 후 종합 리포트 생성 (Phase 2 - V2)
  useEffect(() => {
    if (specialTerms.length > 0 && completedCount === specialTerms.length && reportStatus === "idle") {
      setReportStatus("loading");
      
      const storedContract = sessionStorage.getItem("ade.analysis.contract");
      if (!storedContract) {
        setReportStatus("error");
        return;
      }

      try {
        const contract = JSON.parse(storedContract);
        // 상위 6개 공통 특약은 제외하고 7번째(index 6)부터만 리포트 생성 대상으로 전달
        const targetTerms = specialTerms.slice(6);
        const clausesWithSummaries = targetTerms.map((term, i) => {
          const absoluteIndex = i + 6;
          const res = clauseResults[absoluteIndex];
          return {
            index: absoluteIndex,
            clause: term,
            summaries: res?.llmRelatedLaws || []
          };
        });

        fetch(`${API_BASE}/api/analyze/report_v2`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            property_info: contract.property_info || {},
            common_terms: contract.special_terms?.slice(0, 6) || [],
            clauses_with_summaries: clausesWithSummaries
          }),
        })
        .then(res => {
          if (!res.ok) throw new Error("Report API failed");
          return res.json();
        })
        .then(data => {
          setReportData(data);
          setReportStatus("done");
        })
        .catch(err => {
          console.error("종합 리포트 생성 에러:", err);
          setReportStatus("error");
        });
      } catch (e) {
        console.error("리포트 생성 중 파싱 오류", e);
        setReportStatus("error");
      }
    }
  }, [completedCount, specialTerms.length, clauseResults, reportStatus]);

  const handleTermClick = (index: number) => {
    setViewTab("analysis");
    setTimeout(() => {
      const element = document.getElementById(`analysis-result-${index}`);
      if (element) {
        element.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }, 50);
  };

  const handleRewriteClause = async (
    clauseIdx: number,
    clauseText: string,
    violationLaws: RelatedLaw[],
    allRelatedLaws: RelatedLaw[],
    forceRefresh = false,
  ) => {
    // 캐시 있으면 바로 표시
    if (!forceRefresh && rewriteCache[clauseIdx]) {
      const cached = rewriteCache[clauseIdx];
      setRewriteModal({ clauseIdx, clauseText, violationLaws, allRelatedLaws, status: "done", ...cached });
      return;
    }
    setRewriteModal({ clauseIdx, clauseText, violationLaws, allRelatedLaws, status: "loading" });
    try {
      const res = await fetch(`${API_BASE}/api/analyze/rewrite_clause`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          clause_text: clauseText,
          violation_laws: violationLaws,
          all_related_laws: allRelatedLaws,
        }),
      });
      if (!res.ok) throw new Error("rewrite failed");
      const data = await res.json();
      const result: RewriteCache = { rewrittenClause: data.rewritten_clause, reason: data.reason };
      setRewriteCache(prev => {
        const next = { ...prev, [clauseIdx]: result };
        try { sessionStorage.setItem("ade.rewrite.cache", JSON.stringify(next)); } catch {}
        return next;
      });
      setRewriteModal(prev => prev ? { ...prev, status: "done", ...result } : null);
    } catch {
      setRewriteModal(prev => prev ? { ...prev, status: "error" } : null);
    }
  };

  return (
    <div className="flex flex-col h-screen overflow-hidden" style={{ background: "#F4F3F7" }}>

      {/* 특약 재작성 팝업 */}
      {rewriteModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
        >
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden">

            {/* 헤더 */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-gray-900">✏️ 특약 재작성 제안</h2>
                {/* 새로고침 버튼 + tooltip */}
                {rewriteModal.status !== "loading" && (
                  <div className="relative group/refresh">
                    <button
                      onClick={() => handleRewriteClause(
                        rewriteModal.clauseIdx,
                        rewriteModal.clauseText,
                        rewriteModal.violationLaws,
                        rewriteModal.allRelatedLaws,
                        true,
                      )}
                      className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-blue-500 transition-colors"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M3 21v-5h5"/>
                      </svg>
                    </button>
                    <div className="absolute left-1/2 -translate-x-1/2 top-full mt-1.5 px-2 py-1 rounded bg-gray-800 text-white text-[11px] whitespace-nowrap opacity-0 group-hover/refresh:opacity-100 pointer-events-none transition-opacity z-10">
                      다시 작성하기
                      <div className="absolute left-1/2 -translate-x-1/2 -top-1 w-2 h-2 bg-gray-800 rotate-45" />
                    </div>
                  </div>
                )}
              </div>
              <button
                onClick={() => setRewriteModal(null)}
                className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* 원본 특약 — 고정 */}
            <div className="shrink-0 px-6 pt-4 pb-4 border-b border-gray-100">
              <p className="text-sm font-bold text-red-600 mb-1.5 uppercase tracking-wide">원본 특약</p>
              <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2.5">
                <p className="text-sm text-red-900 leading-relaxed">
                  &ldquo;{rewriteModal.clauseText}&rdquo;
                </p>
              </div>
            </div>

            {/* 재작성된 특약 — 고정 (done 상태) */}
            {rewriteModal.status === "done" && (
              <div className="shrink-0 px-6 pt-4 pb-4 border-b border-gray-100">
                <p className="text-sm font-bold text-blue-700 mb-2 uppercase tracking-wide">재작성된 특약</p>
                <div className="bg-blue-50 border border-blue-200 rounded-xl px-4 py-3">
                  <p className="text-sm text-gray-900 leading-relaxed whitespace-pre-wrap">
                    {rewriteModal.rewrittenClause}
                  </p>
                </div>
              </div>
            )}

            {/* 스크롤 영역 */}
            {rewriteModal.status === "loading" && (
              <div className="flex flex-col items-center justify-center gap-4 py-16 px-6">
                <Loader2 className="w-10 h-10 text-blue-500 animate-spin" />
                <p className="text-sm font-semibold text-gray-700">특약을 재작성하고 있습니다…</p>
                <p className="text-xs text-gray-400">관련 법령을 검토하는 중이에요. 약 1분 소요될 수 있습니다.</p>
              </div>
            )}

            {rewriteModal.status === "error" && (
              <div className="flex flex-col items-center justify-center gap-3 py-16 px-6">
                <AlertCircle className="w-8 h-8 text-red-400" />
                <p className="text-sm text-gray-600">재작성 중 오류가 발생했습니다. 다시 시도해 주세요.</p>
              </div>
            )}

            {rewriteModal.status === "done" && (
              <div className="overflow-y-auto flex-1 px-6 py-5">
                <p className="text-sm font-bold text-gray-900 mb-2 uppercase tracking-wide">재작성 이유 및 근거</p>
                <div className="prose prose-sm max-w-none text-gray-700 prose-li:my-0.5 prose-ul:my-1 prose-p:my-1 [&_strong]:text-gray-900 [&_strong]:font-bold">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{rewriteModal.reason ?? ""}</ReactMarkdown>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <TopNavBar
        mode="analysis"
        fileName={`${fileName} ${specialTerms.length > 0 && analysisStatus === "loading" ? `(분석 중: ${completedCount}/${specialTerms.length})` : ""}`}
        analysisStatus={analysisStatus}
        activeTab="analysis"
      />

      {/* Toast Notifications */}
      <div className="fixed top-24 right-8 z-50 flex flex-col gap-3 pointer-events-none">
        {notifications.map(n => (
          <div 
            key={n.id} 
            className={`flex items-center justify-between gap-4 p-4 bg-white border border-green-200 rounded-xl shadow-xl w-80 pointer-events-auto transition-all duration-500
              ${n.isExiting ? 'opacity-0 translate-x-full' : 'opacity-100 translate-x-0'}`
            }
          >
            <div 
              className="flex-1 cursor-pointer text-sm font-semibold text-gray-800 hover:text-blue-600 transition-colors"
              onClick={() => {
                handleTermClick(n.clauseIdx);
                if (n.timeoutId) clearTimeout(n.timeoutId);
                setNotifications(prev => prev.filter(x => x.id !== n.id));
              }}
            >
              ✅ {n.message}
            </div>
            <button onClick={() => {
                if (n.timeoutId) clearTimeout(n.timeoutId);
                setNotifications(prev => prev.filter(x => x.id !== n.id));
              }} className="text-gray-400 hover:text-gray-600 bg-gray-50 hover:bg-gray-100 rounded-full p-1 transition-colors">
              <X className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>

      <div className="flex flex-row flex-1 min-h-0">
        <DocumentPanel
          specialTerms={specialTerms}
          generalTerms={generalTerms}
          onTermClick={handleTermClick}
          activeIdx={activeClauseIdx}
        />

        <section
          className="flex flex-col flex-1 overflow-hidden"
          style={{ background: "#FAF9FD" }}
        >
          {/* 탭 바 */}
          <div className="px-8 pt-8 pb-0" style={{ background: "#FAF9FD" }}>
            <div className="flex gap-1 p-1 rounded-xl bg-gray-100 self-start inline-flex">
              {(["analysis", "checklist"] as const).map((tab) => (
                <button
                  key={tab}
                  ref={tab === "checklist" ? checklistTabRef : undefined}
                  onClick={() => { setViewTab(tab); if (tab === "checklist") setShowChecklistToast(false); }}
                  className={`px-5 py-2 rounded-lg text-sm font-semibold transition-all ${
                    viewTab === tab
                      ? "bg-white text-gray-900 shadow-sm"
                      : "text-gray-500 hover:text-gray-700"
                  }`}
                >
                  {tab === "analysis" ? "특약 분석" : "체크리스트"}
                  {tab === "checklist" && reportStatus === "loading" && (
                    <Loader2 className="inline-block ml-1.5 h-3 w-3 animate-spin text-blue-500" />
                  )}
                </button>
              ))}
            </div>
          </div>

          {/* 스크롤 가능한 콘텐츠 영역 */}
          <div className="flex flex-col flex-1 overflow-y-auto px-8 pt-8 gap-8" style={{ paddingBottom: "128px" }}>

          {/* 체크리스트 탭 */}
          {viewTab === "checklist" && (
            <>
          {/* 종합 체크리스트 렌더링 */}
          {reportStatus === "loading" && (
            <div className="flex flex-col gap-4 p-6 rounded-xl border bg-blue-50/50 shadow-sm border-blue-100">
              <div className="flex items-center gap-3">
                <Loader2 className="h-5 w-5 animate-spin text-blue-500" />
                <h3 className="text-lg font-bold text-gray-900">종합 분석 보고서 생성 중...</h3>
              </div>
              <p className="text-sm text-gray-500 ml-8">모든 특약의 검색 결과를 바탕으로 계약 전 필수 확인 체크리스트를 만들고 있습니다. 잠시만 기다려주세요.</p>
            </div>
          )}

          {reportStatus === "error" && (
            <div className="flex flex-col gap-4 p-6 rounded-xl border bg-red-50/50 shadow-sm border-red-100">
              <div className="flex items-center gap-3">
                <AlertCircle className="h-5 w-5 text-red-500" />
                <h3 className="text-lg font-bold text-gray-900">종합 분석 보고서 생성 실패</h3>
              </div>
              <p className="text-sm text-red-400 ml-8">보고서 생성 중 오류가 발생했습니다.</p>
            </div>
          )}

          {reportStatus === "done" && reportData && reportData.contract_checklist.length > 0 && (
            <details className="group flex flex-col p-6 rounded-xl border bg-white shadow-sm border-blue-200" open>
              <summary className="flex items-center gap-2 mb-2 cursor-pointer list-none [&::-webkit-details-marker]:hidden select-none outline-none">
                <div className="w-1.5 h-6 bg-blue-600 rounded-full" />
                <h3 className="text-xl font-bold text-gray-900 tracking-tight">계약 전 필수 확인 체크리스트</h3>
                <ChevronDown className="w-5 h-5 text-gray-400 transition-transform rotate-180 group-open:rotate-0 ml-auto" />
              </summary>
              <div className="flex flex-col gap-4 mt-4">
                {reportData.contract_checklist.map((item, idx) => {
                  const relatedClauses = item.basis?.filter(b => b.includes("특약")) ?? [];
                  return (
                  <details key={idx} className="group/check bg-gray-50 border border-gray-100 rounded-lg">
                    <summary className="flex items-start gap-2 p-4 cursor-pointer list-none [&::-webkit-details-marker]:hidden select-none outline-none">
                      <span className="flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-sm font-bold flex-shrink-0 mt-0.5">{idx + 1}</span>
                      <div className="flex flex-col gap-1.5 flex-1 min-w-0">
                        <h4 className="text-base font-semibold text-gray-900">{item.item}</h4>
                        {relatedClauses.length > 0 && (
                          <div className="flex flex-wrap gap-1.5">
                            {relatedClauses.map((c, cIdx) => (
                              <span key={cIdx} className="text-[11px] bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded-full font-medium">{c}</span>
                            ))}
                          </div>
                        )}
                      </div>
                      <ChevronDown className="w-4 h-4 text-gray-400 transition-transform rotate-180 group-open/check:rotate-0 flex-shrink-0 mt-1" />
                    </summary>
                    <div className="p-4 pt-0">
                      <div className="ml-8 prose prose-sm max-w-none text-gray-700 prose-li:my-0.5 prose-ul:my-1 prose-p:my-1 [&_strong]:text-gray-900">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.description ?? ""}</ReactMarkdown>
                      </div>
                      {item.basis && item.basis.length > 0 && (() => {
                      const laws: string[] = [];
                      const precs: string[] = [];
                      const clauses: string[] = [];

                      item.basis.forEach(b => {
                        if (b.includes("특약")) {
                          clauses.push(b);
                        } else if (/[법령조항칙]/.test(b) && !/^\d+[가-힣]+/.test(b)) {
                          laws.push(b.replace(/_/g, ' '));
                        } else {
                          const parts = b.split(",").map(p => p.trim());
                          if (parts.length > 1) {
                            const prefixMatch = parts[0].match(/^(\d+[가-힣]+)/);
                            if (prefixMatch) {
                              const prefix = prefixMatch[1];
                              parts.forEach((p, idx) => {
                                if (idx === 0) precs.push(p);
                                else if (/^\d+$/.test(p)) precs.push(prefix + p);
                                else precs.push(p);
                              });
                            } else {
                              precs.push(...parts);
                            }
                          } else {
                            precs.push(b);
                          }
                        }
                      });

                      return (
                        <div className="ml-8 mt-3 flex flex-col gap-3">
                          
                          {laws.length > 0 && (
                            <details className="group border border-gray-200 rounded-lg overflow-hidden">
                              <summary className="text-sm font-semibold text-gray-700 bg-gray-50 px-4 py-2 cursor-pointer hover:bg-gray-100 select-none">
                                근거 법령
                              </summary>
                              <div className="flex flex-col gap-2 p-4 bg-white border-t border-gray-100">
                                {laws.map((law, lIdx) => (
                                  <div key={`l-${lIdx}`} className="text-sm text-gray-600 flex items-start gap-2">
                                    <span className="w-1.5 h-1.5 rounded-full bg-blue-400 mt-1.5 flex-shrink-0" />
                                    <span>{law}</span>
                                  </div>
                                ))}
                              </div>
                            </details>
                          )}

                          {precs.length > 0 && (
                            <details className="group border border-gray-200 rounded-lg overflow-hidden">
                              <summary className="text-sm font-semibold text-gray-700 bg-gray-50 px-4 py-2 cursor-pointer hover:bg-gray-100 select-none">
                                근거 판례
                              </summary>
                              <div className="flex flex-col gap-2 p-4 bg-white border-t border-gray-100">
                                {precs.map((prec, pIdx) => (
                                  <div key={`p-${pIdx}`} className="text-sm text-gray-600 flex items-start gap-2">
                                    <span className="w-1.5 h-1.5 rounded-full bg-green-400 mt-1.5 flex-shrink-0" />
                                    <span>{prec}</span>
                                  </div>
                                ))}
                              </div>
                            </details>
                          )}
                        </div>
                      );
                    })()}
                    </div>
                  </details>
                  );
                })}
              </div>
            </details>
          )}

          {reportStatus === "idle" && (
            <div className="flex items-center justify-center h-64 text-gray-400 border border-dashed rounded-xl text-sm">
              특약 분석이 완료되면 체크리스트가 생성됩니다.
            </div>
          )}
            </>
          )}

          {/* 특약 분석 탭 */}
          {viewTab === "analysis" && (
            <>
          {/* 개별 특약 렌더링 */}
          {specialTerms.length > 0 && (
            <details className="group flex flex-col p-6 rounded-xl border bg-white shadow-sm border-blue-200" open>
              <summary className="flex items-center gap-2 mb-2 cursor-pointer list-none [&::-webkit-details-marker]:hidden select-none outline-none">
                <div className="w-1.5 h-6 bg-blue-600 rounded-full" />
                <h3 className="text-xl font-bold text-gray-900 tracking-tight">특약 분석 결과</h3>
                <ChevronDown className="w-5 h-5 text-gray-400 transition-transform rotate-180 group-open:rotate-0 ml-auto" />
              </summary>
              <div className="flex flex-col gap-6 mt-4">
                {specialTerms.slice(6).map((term, i) => {
                  const idx = i + 6; // 원래 인덱스 (데이터 조회용)
                  const displayIdx = i + 1; // 표시용 인덱스 (특약 1, 2...)

                  // 법령과 판례 분리 로직 (V2: 개별 특약의 상태에서 가져옴)
                  const llmRelatedLaws = clauseResults[idx]?.llmRelatedLaws || [];
                  const llmLaws = llmRelatedLaws.filter((l: any) => l.type === "법령" || (!l.type && /[법령조항칙]/.test(l.ref))) || [];
                  const llmPrecs = llmRelatedLaws.filter((l: any) => l.type === "판례" || (!l.type && !/[법령조항칙]/.test(l.ref))) || [];
                  
                  // 연관성 분석 로직 (V2: 통합 리포트 데이터에서 가져옴)
                  const llmRelatedClauses = reportData?.related_clauses_map?.[`특약${displayIdx}`] || [];

                  // 판례 제목 포맷팅 함수 (콤마 분리 및 대괄호 처리)
                  const formatPrecTitle = (ref: string) => {
                    const parts = ref.split(",").map(p => p.trim());
                    if (parts.length > 1) {
                      const prefixMatch = parts[0].match(/^(\d+[가-힣]+)/);
                      if (prefixMatch) {
                        const prefix = prefixMatch[1];
                        return parts.map((p, pIdx) => {
                          if (pIdx === 0) return `[${p}]`;
                          if (/^\d+$/.test(p)) return `[${prefix}${p}]`;
                          return `[${p}]`;
                        }).join(", ");
                      }
                    }
                    return `[${ref}]`;
                  };

                  const hasViolation = clauseResults[idx]?.llmRelatedLaws?.some((l: RelatedLaw) => l.is_violation) ?? false;
                  const hasPrecedent = clauseResults[idx]?.llmRelatedLaws?.some((l: RelatedLaw) => l.type === "판례") ?? false;
                  const isDone = clauseResults[idx]?.status === "done";

                  const borderCls = !isDone
                    ? "border-gray-200 border-l-gray-300"
                    : hasViolation
                    ? "border-gray-200 border-l-rose-400"
                    : hasPrecedent
                    ? "border-gray-200 border-l-amber-400"
                    : "border-gray-200 border-l-emerald-400";

                  return (
                    <div
                      key={idx}
                      id={`analysis-result-${idx}`}
                      className={`rounded-xl border border-l-[5px] bg-gray-50/30 scroll-mt-4 overflow-hidden ${borderCls}`}
                      onMouseEnter={() => setActiveClauseIdx(idx)}
                      onMouseLeave={() => setActiveClauseIdx(null)}
                    >
                      <details className="group/item">
                        <summary className="flex items-start justify-between gap-4 p-5 cursor-pointer list-none [&::-webkit-details-marker]:hidden select-none outline-none hover:bg-gray-50 transition-colors">
                          <div className="flex items-center gap-3">
                            <span className="flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-sm font-bold flex-shrink-0">{displayIdx}</span>
                            <h4 className="text-base font-semibold text-gray-900 leading-relaxed">
                              {term}
                            </h4>
                          </div>
                          <div className="flex items-center gap-3 ml-auto">
                            {clauseResults[idx]?.status === "loading" && (
                              <div className="flex items-center gap-2 text-sm text-blue-500 font-medium bg-blue-50 px-3 py-1.5 rounded-full flex-shrink-0">
                                <Loader2 className="h-4 w-4 animate-spin" />
                                분석 중
                              </div>
                            )}
                            {clauseResults[idx]?.status === "error" && (
                              <div className="flex items-center gap-2 text-sm text-red-500 font-medium bg-red-50 px-3 py-1.5 rounded-full flex-shrink-0">
                                <AlertCircle className="h-4 w-4" />
                                분석 실패
                              </div>
                            )}
                            <ChevronDown className="w-5 h-5 text-gray-400 transition-transform rotate-180 group-open/item:rotate-0 flex-shrink-0" />
                          </div>
                        </summary>

                        <div className="p-5 pt-2 border-t border-gray-100 flex flex-col gap-6">

                  {/* 분석 결과 (Phase 1 완료 시 즉시 노출) */}
                  {clauseResults[idx]?.status === "done" && (() => {
                    const anyViolation = llmRelatedLaws.some((l: RelatedLaw) => l.is_violation);

                    return (
                      <div className="flex flex-col gap-4">

                        {/* ① 분석 불릿 섹션 */}
                        <div className="flex flex-col gap-3 p-4 rounded-lg border border-blue-200 bg-blue-50/60">
                          <ul className="flex flex-col gap-3 text-sm leading-relaxed">

                            {/* 한 줄 요약 */}
                            <li className="flex items-start gap-2">
                              <span className="text-blue-500 font-bold shrink-0 mt-0.5">•</span>
                              <div>
                                <strong className="text-gray-900">한 줄 해석: </strong>
                                {clauseResults[idx]?.clauseOneLineSummary
                                  ? <span className="text-gray-700">{clauseResults[idx].clauseOneLineSummary}</span>
                                  : <span className="text-gray-400 italic">해석 정보 없음</span>
                                }
                              </div>
                            </li>

                            {/* 특약 해석 */}
                            <li className="flex items-start gap-2">
                              <span className="text-blue-500 font-bold shrink-0 mt-0.5">•</span>
                              <div className="flex-1">
                                {clauseResults[idx]?.clauseInterpretation ? (
                                  <details className="group/interp">
                                    <summary className="flex items-center gap-1 cursor-pointer select-none list-none w-fit text-gray-900 hover:text-gray-800 transition-colors">
                                      <span className="text-sm font-medium">특약 해석 자세히 보기</span>
                                      <ChevronDown className="w-3.5 h-3.5 transition-transform group-open/interp:rotate-180" />
                                    </summary>
                                    <div className="mt-2 prose prose-sm max-w-none text-gray-700 prose-li:my-0.5 prose-ul:my-1 prose-p:my-1 [&_strong]:text-gray-900">
                                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{clauseResults[idx].clauseInterpretation!}</ReactMarkdown>
                                    </div>
                                  </details>
                                ) : (
                                  <><strong className="text-gray-900">특약 해석: </strong><span className="text-gray-400 italic">해석 정보 없음</span></>
                                )}
                              </div>
                            </li>

                            {/* 주의 사항 */}
                            <li className="flex items-start gap-2">
                              <span className={`font-bold shrink-0 mt-0.5 ${anyViolation ? 'text-red-500' : 'text-blue-500'}`}>•</span>
                              <div className="flex flex-col gap-2 flex-1">
                                <div>
                                  <strong className="text-gray-900">주의 사항: </strong>
                                  {anyViolation ? (
                                    <span className="text-red-600 font-semibold">⚠️ 법령 위배 가능성</span>
                                  ) : (
                                    <span className="text-green-700">특이 사항 없음</span>
                                  )}
                                </div>
                                {anyViolation && (() => {
                                  const violationItems = [...llmLaws, ...llmPrecs].filter((l: any) => l.is_violation && l.summary);
                                  return (
                                    <>
                                      {violationItems.map((law: any, vIdx: number) => {
                                        const parts = law.summary.split(/\n\n+/);
                                        const shortSummary = parts[0]?.trim() ?? "";
                                        const detailedContent = parts.slice(1).join("\n\n").trim();
                                        const isPrec = law.type === "판례";
                                        const refLabel = isPrec ? formatPrecTitle(law.ref) : law.ref.replace(/_/g, ' ');
                                        return (
                                          <div key={`alert-${vIdx}`} className="rounded-lg border border-red-200 bg-red-50 overflow-hidden">
                                            <div className="flex items-center gap-2 px-3 pt-3 pb-1">
                                              <span className="text-base">⚠️</span>
                                              <span className="text-sm font-bold text-red-700">
                                                {refLabel} 위반 가능성
                                              </span>
                                              <span className="ml-auto text-[10px] font-black px-1.5 py-0.5 rounded bg-red-200 text-red-700">위반</span>
                                            </div>
                                            {shortSummary && (
                                              <p className="text-xs text-red-800 px-3 pb-2 leading-relaxed">{shortSummary}</p>
                                            )}
                                            {detailedContent && (
                                              <details className="group/detail">
                                                <summary className="flex items-center justify-between px-3 py-2 text-xs font-semibold text-red-600 hover:bg-red-100 cursor-pointer select-none list-none border-t border-red-100">
                                                  <span>자세히 보기</span>
                                                  <ChevronDown className="w-3 h-3 transition-transform rotate-180 group-open/detail:rotate-0" />
                                                </summary>
                                                <div className="px-3 pb-3 pt-2 prose prose-xs max-w-none prose-li:my-0.5 prose-ul:my-1 border-t border-red-100 text-red-900 [&_strong]:text-red-800">
                                                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{detailedContent}</ReactMarkdown>
                                                </div>
                                              </details>
                                            )}
                                          </div>
                                        );
                                      })}
                                      {/* 특약 재작성 버튼 */}
                                      <button
                                        onClick={() => handleRewriteClause(
                                          idx,
                                          specialTerms[idx],
                                          violationItems,
                                          llmRelatedLaws,
                                        )}
                                        className="w-full mt-1 flex items-center justify-center gap-2 px-3 py-2 rounded-lg border border-red-300 bg-white hover:bg-red-50 text-red-700 text-xs font-semibold transition-colors"
                                      >
                                        ✏️ 법령에 맞게 특약 재작성하기
                                      </button>
                                    </>
                                  );
                                })()}
                              </div>
                            </li>

                          </ul>
                        </div>

                        {/* ① 다른 특약과 연관성 */}
                        {reportStatus === "loading" && (
                          <div className="flex flex-col gap-2">
                            <p className="text-xs font-semibold text-gray-500 px-1">다른 특약과 연관성</p>
                            <div className="flex items-center gap-2 px-1 text-xs text-gray-400">
                              <Loader2 className="h-3 w-3 animate-spin" />
                              <span>연관 특약 분석 중...</span>
                            </div>
                          </div>
                        )}
                        {reportStatus === "done" && llmRelatedClauses.length > 0 && (
                          <div className="flex flex-col gap-2">
                            <p className="text-xs font-semibold text-gray-500 px-1">다른 특약과 연관성</p>
                            <div className="flex flex-wrap gap-1.5">
                              {llmRelatedClauses.map((rel, rIdx) => {
                                const key = `${idx}-rel-${rIdx}`;
                                const isOpen = openPopover === key;
                                return (
                                  <button
                                    key={key}
                                    onClick={() => setOpenPopover(isOpen ? null : key)}
                                    className={`text-xs px-2.5 py-1 rounded-full border font-medium transition-colors ${
                                      isOpen
                                        ? "border-orange-400 bg-orange-100 text-orange-800"
                                        : "border-orange-200 bg-orange-50 text-orange-700 hover:bg-orange-100"
                                    }`}
                                  >
                                    {rel.clause_id}
                                  </button>
                                );
                              })}
                            </div>
                            {/* 말풍선 팝오버 */}
                            {llmRelatedClauses.map((rel, rIdx) => {
                              const key = `${idx}-rel-${rIdx}`;
                              if (openPopover !== key) return null;
                              return (
                                <div key={`pop-${key}`} className="relative mt-1">
                                  <div className="absolute left-4 -top-2 w-3 h-3 rotate-45 border-t border-l border-gray-200 bg-white z-10" />
                                  <div className="relative z-20 rounded-xl border border-gray-200 bg-white shadow-lg p-4 flex flex-col gap-2">
                                    {rel.clause_text && (
                                      <p className="text-xs text-gray-500 leading-relaxed border-b border-gray-100 pb-2">
                                        &ldquo;{rel.clause_text}&rdquo;
                                      </p>
                                    )}
                                    <p className="text-sm text-gray-700 leading-relaxed">{rel.relation}</p>
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}

                        {/* ② 관련 법령 */}
                        {llmLaws.length > 0 && (
                          <div className="flex flex-col gap-2">
                            <p className="text-xs font-semibold text-gray-500 px-1">관련 법령</p>
                            <div className="flex flex-wrap gap-1.5">
                              {llmLaws.map((law, lIdx) => {
                                const key = `${idx}-law-${lIdx}`;
                                const isOpen = openPopover === key;
                                return (
                                  <button
                                    key={key}
                                    onClick={() => setOpenPopover(isOpen ? null : key)}
                                    className={`text-xs px-2.5 py-1 rounded-full border font-medium transition-colors ${
                                      law.is_violation
                                        ? "border-red-300 bg-red-50 text-red-700 hover:bg-red-100"
                                        : isOpen
                                        ? "border-blue-400 bg-blue-100 text-blue-800"
                                        : "border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100"
                                    }`}
                                  >
                                    {law.ref.replace(/_/g, ' ')}
                                    {law.is_violation && <span className="ml-1 text-red-500">⚠️</span>}
                                  </button>
                                );
                              })}
                            </div>
                            {/* 말풍선 팝오버 */}
                            {llmLaws.map((law, lIdx) => {
                              const key = `${idx}-law-${lIdx}`;
                              if (openPopover !== key) return null;
                              return (
                                <div key={`pop-${key}`} className="relative mt-1">
                                  <div className="absolute left-4 -top-2 w-3 h-3 rotate-45 border-t border-l border-gray-200 bg-white z-10" />
                                  <div className="relative z-20 rounded-xl border border-gray-200 bg-white shadow-lg p-4 text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
                                    {law.content || "원문 정보 없음"}
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}

                        {/* ③ 유사한 분쟁 사례 */}
                        {llmPrecs.length > 0 && (
                          <div className="flex flex-col gap-2">
                            <p className="text-xs font-semibold text-gray-500 px-1">유사한 분쟁 사례</p>
                            <div className="flex flex-wrap gap-1.5">
                              {llmPrecs.map((prec, pIdx) => {
                                const key = `${idx}-prec-${pIdx}`;
                                const isOpen = openPopover === key;
                                return (
                                  <button
                                    key={key}
                                    onClick={() => setOpenPopover(isOpen ? null : key)}
                                    className={`text-xs px-2.5 py-1 rounded-full border font-medium transition-colors ${
                                      prec.is_violation
                                        ? "border-red-300 bg-red-50 text-red-700 hover:bg-red-100"
                                        : isOpen
                                        ? "border-green-500 bg-green-100 text-green-800"
                                        : "border-green-200 bg-green-50 text-green-700 hover:bg-green-100"
                                    }`}
                                  >
                                    {formatPrecTitle(prec.ref)}
                                    {prec.is_violation && <span className="ml-1 text-red-500">⚠️</span>}
                                  </button>
                                );
                              })}
                            </div>
                            {/* 말풍선 팝오버 */}
                            {llmPrecs.map((prec, pIdx) => {
                              const key = `${idx}-prec-${pIdx}`;
                              if (openPopover !== key) return null;
                              return (
                                <div key={`pop-${key}`} className="relative mt-1">
                                  <div className="absolute left-4 -top-2 w-3 h-3 rotate-45 border-t border-l border-gray-200 bg-white z-10" />
                                  <div className="relative z-20 rounded-xl border border-gray-200 bg-white shadow-lg p-4">
                                    {prec.summary
                                      ? <div className="prose prose-sm max-w-none text-gray-700 prose-li:my-0.5 prose-ul:my-1 prose-p:my-0.5 [&_strong]:text-gray-900"><ReactMarkdown remarkPlugins={[remarkGfm]}>{prec.summary}</ReactMarkdown></div>
                                      : <p className="text-sm text-gray-400">내용 없음</p>
                                    }
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        )}

                      </div>
                    );
                  })()}

                  {/* 분석 결과 (로딩 완료 시에만) - 관련 법령/판례 20개 표시 부분 제거 요청으로 주석 처리
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
                  */}
                        </div>
                      </details>
                    </div>
                  );
                })}
              </div>
            </details>
          )}

          {!specialTerms.length && (
            <div className="flex items-center justify-center h-64 text-gray-500 border border-dashed rounded-xl">
              분석할 특약사항이 없습니다.
            </div>
          )}
            </>
          )}
          </div>{/* end scrollable content */}
        </section>

      {/* 체크리스트 완료 말풍선 — position:fixed로 overflow 클리핑 완전 우회 */}
      {showChecklistToast && toastPos && !rewriteModal && (
        <div
          className="fixed z-[9999] whitespace-nowrap"
          style={{
            left: toastPos.left,
            top: toastPos.top - 8,
            transform: "translate(-50%, -100%)",
          }}
        >
          <div
            className="flex items-center gap-2 px-3 py-2 rounded-xl bg-white border border-green-200 shadow-lg text-sm text-green-800 font-medium cursor-pointer hover:bg-green-50 transition-colors"
            onClick={() => { setShowChecklistToast(false); setViewTab("checklist"); }}
          >
            <span>✅</span>
            <span>체크리스트 작성 완료!</span>
            <button
              onClick={(e) => { e.stopPropagation(); setShowChecklistToast(false); }}
              className="ml-0.5 text-green-400 hover:text-green-700 transition-colors font-bold leading-none"
              aria-label="닫기"
            >
              ×
            </button>
          </div>
          {/* 아래쪽 화살표 */}
          <div className="absolute left-1/2 -translate-x-1/2 -bottom-[5px] w-2.5 h-2.5 rotate-45 border-b border-r border-green-200 bg-white z-10" />
        </div>
      )}
      </div>

      {/* <BottomActionBar onChatbot={() => setIsChatOpen(true)} /> */}
      
      {/* 챗봇 컴포넌트 */}
      <ChatBot
        isOpen={isChatOpen}
        onOpen={() => setIsChatOpen(true)}
        onClose={() => setIsChatOpen(false)}
        showNudge={analysisStatus === "done" && !isChatOpen}
        context={{
          report: reportData,
          clauses: Object.values(clauseResults).map(res => ({
            laws: res.llmRelatedLaws,
            status: res.status
          })),
          rewrittenClauses: Object.entries(rewriteCache).reduce<Record<string, { rewrittenClause: string; reason: string }>>((acc, [idxStr, val]) => {
            const idx = Number(idxStr);
            const displayIdx = idx - 6 + 1; // 특약 N (공통특약 제외)
            acc[`특약${displayIdx}`] = val;
            return acc;
          }, {}),
          rawContract: typeof window !== "undefined" ? JSON.parse(sessionStorage.getItem("ade.analysis.contract") || "{}") : null
        }}
      />
    </div>
  );
}
