import type { Clause } from "@/types/contract";

type ClauseItemProps = {
  clause: Clause;
  selected: boolean;
  onSelect: () => void;
};

export function ClauseItem({ clause, selected, onSelect }: ClauseItemProps) {
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
        <span
          className={`mt-2 block text-[13px] leading-[1.65] text-text-primary/92 ${
            selected ? "whitespace-pre-wrap" : "truncate"
          }`}
        >
          {clause.body}
        </span>
      </div>
    </button>
  );
}
