"use client";

import { useMemo, useState } from "react";
import type { ContractMock } from "@/types/contract";
import { DocumentPanel } from "@/components/analysis/DocumentPanel";
import { AnalysisPanel } from "@/components/analysis/AnalysisPanel";
import { ChatbotPanel } from "@/components/analysis/ChatbotPanel";

export function ContractAnalysisView({ contract }: { contract: ContractMock }) {
  const firstId = contract.clauses[0]?.id ?? "";
  const [selectedClauseId, setSelectedClauseId] = useState(firstId);

  const selectedClause = useMemo(
    () => contract.clauses.find((c) => c.id === selectedClauseId) ?? null,
    [contract.clauses, selectedClauseId],
  );

  return (
    <div className="flex h-full min-h-0 w-full flex-1 flex-col overflow-hidden">
      <div className="grid min-h-0 flex-1 grid-rows-2 gap-0 overflow-hidden border-border-default lg:grid-cols-2 lg:grid-rows-1">
        <div className="min-h-0 overflow-hidden border-b border-border-default lg:border-b-0 lg:border-r lg:border-border-default">
          <DocumentPanel
            title={contract.title}
            leaseType={contract.lease_type}
            propertyInfo={contract.property_info}
            clauses={contract.clauses}
            selectedClauseId={selectedClauseId}
            onSelectClause={setSelectedClauseId}
          />
        </div>
        <div className="relative min-h-0 overflow-hidden">
          <AnalysisPanel clause={selectedClause} />
        </div>
      </div>
      <ChatbotPanel />
    </div>
  );
}
