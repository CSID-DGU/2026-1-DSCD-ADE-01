import type { RecentDocument } from "@/types/contract";
import { RecentDocumentCard } from "@/components/upload/RecentDocumentCard";

export function RecentDocumentPanel({ documents }: { documents: RecentDocument[] }) {
  return (
    <aside className="flex h-full min-h-0 w-full flex-col gap-4 overflow-y-auto lg:w-[320px] lg:shrink-0 lg:border-l lg:border-border-default lg:bg-white/40 lg:pl-6">
      <h3 className="text-base font-semibold text-text-primary">최근 문서</h3>
      <ul className="flex flex-col gap-3">
        {documents.map((doc) => (
          <li key={doc.id}>
            <RecentDocumentCard doc={doc} />
          </li>
        ))}
      </ul>
    </aside>
  );
}
