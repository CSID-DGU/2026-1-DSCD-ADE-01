"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Header } from "@/components/Header";
import { ContractAnalysisView } from "@/components/analysis/ContractAnalysisView";
import {
  loadStoredContractResult,
  loadV1Meta,
  type V1ResultMeta,
} from "@/lib/contractResultAdapter";
import type { ContractMock } from "@/types/contract";

export function ContractAnalysisPageClient() {
  const [contract, setContract] = useState<ContractMock | null>(null);
  const [hasLoadError, setHasLoadError] = useState(false);
  const [v1Meta, setV1Meta] = useState<V1ResultMeta | null>(null);

  useEffect(() => {
    const stored = loadStoredContractResult();
    if (!stored) {
      setHasLoadError(true);
      return;
    }
    setContract(stored);
    setV1Meta(loadV1Meta());
  }, []);

  if (!contract) {
    return (
      <div className="flex h-screen min-h-0 flex-col overflow-hidden bg-page-bg">
        <Header context="analysis" showAnalysisStatus={false} />
        <main className="flex min-h-0 flex-1 items-center justify-center px-6">
          <div className="w-full max-w-lg rounded-xl border border-border-default bg-white p-6 text-center">
            <h1 className="text-lg font-semibold text-text-primary">분석 결과를 불러올 수 없습니다</h1>
            <p className="mt-2 text-sm text-text-secondary">
              {hasLoadError
                ? "분석 결과가 없거나 손상되었습니다. 다시 업로드 후 분석을 진행해 주세요."
                : "분석 결과를 불러오는 중입니다."}
            </p>
            {hasLoadError ? (
              <Link
                href="/"
                className="mt-5 inline-flex rounded-lg bg-primary-navy px-4 py-2 text-sm font-medium text-white"
              >
                업로드 페이지로 이동
              </Link>
            ) : null}
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="flex h-screen min-h-0 flex-col overflow-hidden bg-page-bg">
      <Header
        context="analysis"
        fileDisplayName={contract.displayFileName}
        showAnalysisStatus
        analysisStatusLabel="v1 파싱·확장 완료"
      />
      <div className="shrink-0 border-b border-border-default bg-amber-50 px-4 py-2 text-center text-xs leading-relaxed text-amber-950 sm:px-6">
        <strong className="font-semibold">v1 결과 화면</strong>
        {": "}
        현재 표시되는 것은 계약서 파싱과 특약 Query Expansion까지입니다. 관련 법령·판례 검색 및 LLM 기반 최종 보완 가이드는
        RAG/LLM 단계 연동 후 이 영역에 채워질 예정입니다.
      </div>
      {v1Meta?.expansionSkipped ? (
        <div className="shrink-0 border-b border-amber-200 bg-amber-100/80 px-4 py-2 text-center text-[11px] leading-relaxed text-amber-950 sm:px-6">
          특약 Query Expansion 단계는 서버에서 실패하여 <strong className="font-semibold">파싱 결과만</strong> 표시합니다.
          특약 보완 문구가 비어 있을 수 있습니다.{" "}
          {v1Meta.expansionSkipReason ? (
            <span className="block max-w-3xl truncate sm:mx-auto sm:whitespace-normal">
              (서버 메시지 요약: {v1Meta.expansionSkipReason.slice(0, 200)}
              {v1Meta.expansionSkipReason.length > 200 ? "…" : ""})
            </span>
          ) : null}
        </div>
      ) : null}
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <ContractAnalysisView contract={contract} />
      </main>
    </div>
  );
}
