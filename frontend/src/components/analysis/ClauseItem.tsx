import type { Clause } from "@/types/contract";
import { extractClauseFields, extractLeasePaymentTable } from "@/lib/clauseStructuring";

type ClauseItemProps = {
  clause: Clause;
  selected: boolean;
  onSelect: () => void;
};

export function ClauseItem({ clause, selected, onSelect }: ClauseItemProps) {
  const fields = extractClauseFields(clause.body).slice(0, 3);
  const paymentTable = selected ? extractLeasePaymentTable(clause.body) : null;

  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full border-0 py-3 pl-1 pr-2 text-left transition ${
        selected
          ? "bg-[#E8F1FF] shadow-[inset_3px_0_0_0_#002045]"
          : "bg-white hover:bg-[#FAFAFA]"
      }`}
    >
      <div className="px-3">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span className="text-sm font-bold tracking-tight text-text-primary">{clause.label}</span>
          {clause.title ? (
            <span className="text-xs font-semibold text-text-secondary">({clause.title})</span>
          ) : null}
        </div>
        {paymentTable ? (
          <div className="mt-2 rounded-md border border-border-default bg-white">
            {paymentTable.intro ? (
              <p className="border-b border-border-default px-2.5 py-2 text-[12.5px] leading-relaxed text-text-primary/92">
                {paymentTable.intro}
              </p>
            ) : null}
            <dl className="grid grid-cols-[88px_1fr] text-[12.5px] leading-relaxed">
              {paymentTable.rows.map((row) => (
                <div key={row.label} className="contents">
                  <dt className="border-b border-r border-border-default bg-page-bg px-2 py-1.5 font-semibold text-text-primary">
                    {row.label}
                  </dt>
                  <dd className="border-b border-border-default px-2 py-1.5 text-text-primary/92">{row.value}</dd>
                </div>
              ))}
            </dl>
          </div>
        ) : (
          <span
            className="mt-2 block whitespace-pre-wrap text-[13px] leading-[1.65] text-text-primary/92"
            style={
              selected
                ? undefined
                : {
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }
            }
          >
            {clause.body}
          </span>
        )}
        {fields.length > 0 ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {fields.map((f) => (
              <span
                key={f.label}
                className="rounded-md border border-border-default bg-white px-2 py-0.5 text-[11px] text-text-secondary"
              >
                {f.label} {f.value}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </button>
  );
}
