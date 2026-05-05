import { Header } from "@/components/Header";
import { ContractAnalysisView } from "@/components/analysis/ContractAnalysisView";
import { mockContract } from "@/data/mockContract";

export default function ContractAnalysisPage() {
  return (
    <div className="flex h-screen min-h-0 flex-col overflow-hidden bg-page-bg">
      <Header
        context="analysis"
        fileDisplayName={mockContract.displayFileName}
        showAnalysisStatus
        analysisStatusLabel="분석 완료"
      />
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <ContractAnalysisView contract={mockContract} />
      </main>
    </div>
  );
}
