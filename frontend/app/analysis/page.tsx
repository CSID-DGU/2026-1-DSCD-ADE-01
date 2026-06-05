"use client";

import { useEffect, useState } from "react";
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
          initialResults[i] = { laws: [], precedents: [], rawLaws: [], rawPrecs: [], llmRelatedLaws: [], status: "loading" };
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
        />

        <section
          className="flex flex-col flex-1 overflow-y-auto px-8 py-8 gap-8"
          style={{ background: "#FAF9FD", paddingBottom: "128px" }}
        >
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
                {reportData.contract_checklist.map((item, idx) => (
                  <details key={idx} className="group/check bg-gray-50 border border-gray-100 rounded-lg">
                    <summary className="flex items-center gap-2 p-4 cursor-pointer list-none [&::-webkit-details-marker]:hidden select-none outline-none">
                      <span className="flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-700 text-sm font-bold flex-shrink-0">{idx + 1}</span>
                      <h4 className="text-base font-semibold text-gray-900">{item.item}</h4>
                      <ChevronDown className="w-4 h-4 text-gray-400 transition-transform rotate-180 group-open/check:rotate-0 ml-auto flex-shrink-0" />
                    </summary>
                    <div className="p-4 pt-0">
                      <p className="text-sm text-gray-700 leading-relaxed ml-8">{item.description}</p>
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
                          {clauses.length > 0 && (
                            <div className="flex flex-wrap gap-2">
                              {clauses.map((c, cIdx) => (
                                <span key={`c-${cIdx}`} className="text-xs bg-gray-200 text-gray-700 px-2 py-1 rounded-md font-medium">{c}</span>
                              ))}
                            </div>
                          )}
                          
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
                ))}
              </div>
            </details>
          )}

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

                  return (
                    <div 
                      key={idx} 
                      id={`analysis-result-${idx}`}
                      className="rounded-xl border bg-gray-50/30 scroll-mt-4 overflow-hidden"
                      style={{ borderColor: "#E2E8F0" }}
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

                  {/* LLM 요약 (Phase 1 완료 시 즉시 노출) */}
                  {clauseResults[idx]?.status === "done" && (
                    <div className="flex flex-col gap-3">
                      {llmLaws.length > 0 && (
                        <details className="group/laws border border-blue-200 rounded-lg overflow-hidden">
                          <summary className="flex items-center justify-between text-sm font-semibold text-blue-900 bg-blue-50 px-4 py-3 cursor-pointer hover:bg-blue-100 select-none list-none">
                            <span>관련된 법령</span>
                            <ChevronDown className="w-4 h-4 text-blue-400 transition-transform rotate-180 group-open/laws:rotate-0" />
                          </summary>
                          <div className="flex flex-col gap-4 p-4 bg-white border-t border-blue-100">
                            {llmLaws.map((law, lIdx) => (
                              law.summary && (
                                <div key={`law-sum-${lIdx}`} className="text-sm text-gray-700 leading-relaxed">
                                  <strong className={`flex items-center gap-2 mb-2 ${law.is_violation ? 'text-red-600' : 'text-gray-900'}`}>
                                    [{law.ref.replace(/_/g, ' ')}]
                                    {law.is_violation && (
                                      <span className="px-1.5 py-0.5 rounded bg-red-600 text-[10px] font-black text-white uppercase tracking-tighter">
                                        주의
                                      </span>
                                    )}
                                  </strong>
                                  {law.content && (
                                    <details className="group/raw-law mt-3 p-3 bg-gray-50 border border-gray-100 rounded-lg">
                                      <summary className="flex items-center justify-between text-xs font-semibold text-gray-700 cursor-pointer select-none list-none">
                                        <span>원문 보기</span>
                                        <ChevronDown className="w-3 h-3 text-gray-400 transition-transform rotate-180 group-open/raw-law:rotate-0" />
                                      </summary>
                                      <p className="mt-2 text-xs whitespace-pre-wrap text-gray-600">
                                        {law.content}
                                      </p>
                                    </details>
                                  )}
                                  {law.is_violation ? (
                                    <div className="mt-3 p-4 bg-red-50 border border-red-100 rounded-lg flex flex-col gap-2">
                                      <div className="flex items-center gap-2 text-red-600 font-bold text-xs">
                                        <AlertCircle className="w-4 h-4" />
                                        <span>주의 사항 및 이유</span>
                                      </div>
                                      <p className="whitespace-pre-wrap text-red-900 font-medium">{law.summary}</p>
                                    </div>
                                  ) : (
                                    <p className="whitespace-pre-wrap mt-2">{law.summary}</p>
                                  )}
                                </div>
                              )
                            ))}
                          </div>
                        </details>
                      )}

                      {llmPrecs.length > 0 && (
                        <details className="group/precs border border-green-200 rounded-lg overflow-hidden">
                          <summary className="flex items-center justify-between text-sm font-semibold text-green-900 bg-green-50 px-4 py-3 cursor-pointer hover:bg-green-100 select-none list-none">
                            <span>유사한 분쟁 사례</span>
                            <ChevronDown className="w-4 h-4 text-green-400 transition-transform rotate-180 group-open/precs:rotate-0" />
                          </summary>
                          <div className="flex flex-col gap-4 p-4 bg-white border-t border-green-100">
                            {llmPrecs.map((prec, pIdx) => (
                              prec.summary && (
                                <div key={`prec-sum-${pIdx}`} className="text-sm text-gray-700 leading-relaxed">
                                  <strong className={`flex items-center gap-2 mb-2 ${prec.is_violation ? 'text-red-600' : 'text-gray-900'}`}>
                                    {formatPrecTitle(prec.ref)}
                                    {prec.is_violation && (
                                      <span className="px-1.5 py-0.5 rounded bg-red-600 text-[10px] font-black text-white uppercase tracking-tighter">
                                        주의
                                      </span>
                                    )}
                                  </strong>
                                  {prec.content && (
                                    <details className="group/raw-prec mt-3 p-3 bg-gray-50 border border-gray-100 rounded-lg">
                                      <summary className="flex items-center justify-between text-xs font-semibold text-gray-700 cursor-pointer select-none list-none">
                                        <span>판결 요지 보기</span>
                                        <ChevronDown className="w-3 h-3 text-gray-400 transition-transform rotate-180 group-open/raw-prec:rotate-0" />
                                      </summary>
                                      <p className="mt-2 text-xs whitespace-pre-wrap text-gray-600">
                                        {prec.content}
                                      </p>
                                    </details>
                                  )}
                                  {prec.is_violation ? (
                                    <div className="mt-3 p-4 bg-red-50 border border-red-100 rounded-lg flex flex-col gap-2">
                                      <div className="flex items-center gap-2 text-red-600 font-bold text-xs">
                                        <AlertCircle className="w-4 h-4" />
                                        <span>주의 사항 및 이유</span>
                                      </div>
                                      <p className="whitespace-pre-wrap text-red-900 font-medium">{prec.summary}</p>
                                    </div>
                                  ) : (
                                    <p className="whitespace-pre-wrap mt-2">{prec.summary}</p>
                                  )}
                                </div>
                              )
                            ))}
                          </div>
                        </details>
                      )}

                      {/* 연관성 주의 (Phase 2 완료 후 노출) */}
                      {reportStatus === "done" && llmRelatedClauses.length > 0 && (
                        <details className="group/rel border border-orange-200 rounded-lg overflow-hidden">
                          <summary className="flex items-center justify-between text-sm font-semibold text-orange-900 bg-orange-50 px-4 py-3 cursor-pointer hover:bg-orange-100 select-none list-none">
                            <span>함께 확인해야 할 특약</span>
                            <ChevronDown className="w-4 h-4 text-orange-400 transition-transform rotate-180 group-open/rel:rotate-0" />
                          </summary>
                          <div className="flex flex-col gap-4 p-4 bg-white border-t border-orange-100">
                            <ul className="list-disc pl-5 space-y-4 text-sm text-gray-700 leading-relaxed">
                              {llmRelatedClauses.map((rel, rIdx) => (
                                <li key={`rel-${rIdx}`}>
                                  <strong className="block text-gray-900 mb-2">[{rel.clause_id}] "{rel.clause_text}"</strong>
                                  <p className="whitespace-pre-wrap">{rel.relation}</p>
                                </li>
                              ))}
                            </ul>
                          </div>
                        </details>
                      )}
                    </div>
                  )}

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
        </section>
      </div>

      {/* <BottomActionBar onChatbot={() => setIsChatOpen(true)} /> */}
      
      {/* 챗봇 컴포넌트 */}
      <ChatBot 
        isOpen={isChatOpen}
        onOpen={() => setIsChatOpen(true)}
        onClose={() => setIsChatOpen(false)}
        context={{
          report: reportData,
          clauses: Object.values(clauseResults).map(res => ({
            laws: res.llmRelatedLaws,
            status: res.status
          })),
          rawContract: typeof window !== "undefined" ? JSON.parse(sessionStorage.getItem("ade.analysis.contract") || "{}") : null
        }}
      />
    </div>
  );
}
