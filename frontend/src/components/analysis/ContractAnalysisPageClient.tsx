"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Header } from "@/components/Header";
import { ContractAnalysisView } from "@/components/analysis/ContractAnalysisView";
import { loadStoredContractResult } from "@/lib/contractResultAdapter";
import type { ContractMock } from "@/types/contract";

export function ContractAnalysisPageClient() {
  const [contract, setContract] = useState<ContractMock | null>(null);
  const [hasLoadError, setHasLoadError] = useState(false);

  useEffect(() => {
    const stored = loadStoredContractResult();
    if (!stored) {
      setHasLoadError(true);
      return;
    }
    setContract(stored);
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
        analysisStatusLabel="분석 완료"
      />
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <ContractAnalysisView contract={contract} />
      </main>
    </div>
  );
}
