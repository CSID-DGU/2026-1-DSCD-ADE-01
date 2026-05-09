import type { Clause, PropertyInfo } from "@/types/contract";
import { ClauseItem } from "@/components/analysis/ClauseItem";

type DocumentPanelProps = {
  /** 상단에 따로 쓰일 계약서 표제 (파일/주소 요약 등) */
  title: string;
  leaseType?: string;
  propertyInfo?: PropertyInfo;
  clauses: Clause[];
  selectedClauseId: string;
  onSelectClause: (id: string) => void;
};

function dash(val: string | undefined) {
  const t = val?.trim();
  return t ? t : "-";
}

function ContractPropertySummary({
  leaseType,
  propertyInfo,
}: {
  leaseType?: string;
  propertyInfo?: PropertyInfo;
}) {
  const p = propertyInfo ?? {};
  const rows: { k: string; v: string }[] = [
    { k: "계약 유형", v: dash(p.lease_category || leaseType) },
    { k: "주소", v: dash(p.address) },
    { k: "건물 유형", v: dash(p.building_type) },
    { k: "임차 부분", v: dash(p.leased_part) },
    { k: "계약 종류", v: dash(p.contract_type) },
    { k: "보증금", v: dash(p.deposit) },
    { k: "월세", v: dash(p.monthly_rent) },
    { k: "체납/선순위 확정일자", v: dash(p.arrear_or_priority_registered) },
  ];

  return (
    <details className="rounded-md border border-border-default bg-white shadow-sm open:shadow-none">
      <summary className="cursor-pointer list-none px-3 py-2.5 text-xs font-semibold text-text-primary [&::-webkit-details-marker]:hidden">
        <span className="inline-flex items-center gap-2">
          계약서 기본 정보
          <span className="text-[10px] font-normal uppercase tracking-wide text-text-secondary">
            (접기/펼치기)
          </span>
        </span>
      </summary>
      <dl className="grid gap-2 border-t border-border-default px-3 py-3 sm:grid-cols-2">
        {rows.map(({ k, v }) => (
          <div key={k} className="min-w-0">
            <dt className="text-[11px] font-medium text-text-secondary">{k}</dt>
            <dd className="mt-0.5 text-sm leading-snug text-text-primary">{v}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

export function DocumentPanel({
  title,
  leaseType,
  propertyInfo,
  clauses,
  selectedClauseId,
  onSelectClause,
}: DocumentPanelProps) {
  const general = clauses.filter((c) => c.group === "general_terms");
  const special = clauses.filter((c) => c.group === "special_terms");

  const renderGroup = (label: string, list: Clause[], defaultOpen = true) => {
    if (list.length === 0) return null;
    return (
      <details className="mt-4 first:mt-0 rounded-md border border-border-default bg-white" open={defaultOpen}>
        <summary className="cursor-pointer list-none px-3 py-2.5 [&::-webkit-details-marker]:hidden">
          <span className="inline-flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-text-secondary">
            {label}
            <span className="rounded bg-page-bg px-1.5 py-0.5 text-[10px] text-text-secondary/90">
              {list.length}개
            </span>
          </span>
        </summary>
        <div className="border-t border-border-default">
          <p className="sr-only">
            계약서 조항. 항목을 선택하면 우측 분석 패널이 갱신됩니다.
          </p>
          <ul className="divide-y divide-border-default">
            {list.map((c) => (
              <li key={c.id}>
                <ClauseItem
                  clause={c}
                  selected={c.id === selectedClauseId}
                  onSelect={() => onSelectClause(c.id)}
                />
              </li>
            ))}
          </ul>
        </div>
      </details>
    );
  };

  return (
    <div className="flex h-full min-h-0 w-full flex-col bg-page-bg">
      <div className="shrink-0 border-b border-border-default bg-page-bg px-3 pb-2.5 pt-3 sm:px-5">
        <h2 className="text-center text-[15px] font-bold tracking-tight text-text-primary">
          표준 주택임대차계약서
        </h2>
        <p className="mt-1 text-center text-[10px] uppercase tracking-wide text-text-secondary">
          Standard Residential Lease Agreement
        </p>
        <p
          className="mt-2.5 truncate border-t border-dashed border-border-default pt-2.5 text-center text-[13px] font-semibold text-text-primary"
          title={title}
        >
          {title}
        </p>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto overscroll-contain px-3 pb-3 pt-2 sm:px-5">
        <ContractPropertySummary leaseType={leaseType} propertyInfo={propertyInfo} />

        {renderGroup("기본 조항", general, true)}
        {renderGroup("특약 사항", special, true)}
      </div>
    </div>
  );
}
