import Link from "next/link";
import type { RecentDocument } from "@/types/contract";
import { ChevronRight } from "lucide-react";

export function RecentDocumentCard({ doc }: { doc: RecentDocument }) {
  return (
    <article className="rounded-lg border border-border-default bg-white p-4 shadow-sm transition hover:border-primary-navy/30">
      <h4 className="text-sm font-medium leading-snug text-text-primary">{doc.title}</h4>
      <p className="mt-1 text-xs text-text-secondary">업데이트 {doc.updatedAt}</p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Link
          href="/contract-analysis"
          className="inline-flex items-center gap-1 text-xs font-medium text-primary-navy hover:underline"
        >
          View Analysis
          <ChevronRight className="h-3.5 w-3.5" aria-hidden />
        </Link>
        <button
          type="button"
          disabled
          className="rounded-md border border-border-default bg-panel-bg px-2.5 py-1 text-xs font-medium text-text-secondary opacity-60"
          title="추후 연결 예정"
        >
          재분석
        </button>
      </div>
    </article>
  );
}
