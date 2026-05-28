"use client";

import { ChevronRight } from "lucide-react";

type Document = {
  id: string;
  name: string;
  date: string;
  size: string;
};

const MOCK_DOCUMENTS: Document[] = [
  { id: "1", name: "공덕동_임대차계약서.pdf", date: "Oct 25, 2026", size: "2.4 MB" },
  { id: "2", name: "성북동_임대차계약서(1).docx", date: "Oct 22, 2026", size: "1.1 MB" },
  { id: "3", name: "이사할_집_계약서.pdf", date: "Oct 20, 2026", size: "845 KB" },
];

function RecentDocumentCard({ doc }: { doc: Document }) {
  return (
    <article
      className="rounded-lg border p-4 shadow-sm transition"
      style={{
        background: "white",
        borderColor: "#E2E8F0",
      }}
      onMouseEnter={(e) => {
        (e.currentTarget as HTMLElement).style.borderColor = "rgba(0,32,69,0.3)";
      }}
      onMouseLeave={(e) => {
        (e.currentTarget as HTMLElement).style.borderColor = "#E2E8F0";
      }}
    >
      <h4
        className="text-sm font-medium leading-snug"
        style={{ color: "#1A1C1E", fontFamily: "var(--font-public-sans)" }}
      >
        {doc.name}
      </h4>
      <p
        className="mt-1 text-xs"
        style={{ color: "#74777F", fontFamily: "var(--font-public-sans)" }}
      >
        {doc.date} · {doc.size}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="inline-flex items-center gap-1 text-xs font-medium hover:underline"
          style={{ color: "#002045", fontFamily: "var(--font-public-sans)" }}
        >
          View Analysis
          <ChevronRight className="h-3.5 w-3.5" aria-hidden />
        </button>
        <button
          type="button"
          disabled
          className="rounded-md border px-2.5 py-1 text-xs font-medium opacity-60"
          style={{
            background: "#FAF9FD",
            borderColor: "#E2E8F0",
            color: "#43474E",
            fontFamily: "var(--font-public-sans)",
          }}
          title="추후 연결 예정"
        >
          재분석
        </button>
      </div>
    </article>
  );
}

export function RecentDocumentPanel() {
  return (
    <aside
      className="flex h-full min-h-0 w-full flex-col gap-4 overflow-y-auto lg:w-[320px] lg:shrink-0 lg:border-l lg:pl-6"
      style={{ borderColor: "#E2E8F0" }}
    >
      <h3
        className="text-base font-semibold"
        style={{ color: "#1A1C1E", fontFamily: "var(--font-public-sans)" }}
      >
        최근 문서
      </h3>
      <ul className="flex flex-col gap-3">
        {MOCK_DOCUMENTS.map((doc) => (
          <li key={doc.id}>
            <RecentDocumentCard doc={doc} />
          </li>
        ))}
      </ul>
    </aside>
  );
}
