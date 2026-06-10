"use client";

import { useEffect, useState } from "react";
import { ChevronRight, FileText, Loader2, X } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

type DocumentHistoryItem = {
  doc_id: string;
  file_name: string;
  created_at: string;
};

function RecentDocumentCard({ 
  doc, 
  onSelect,
  onDelete,
  isSelecting,
  isDeleting
}: { 
  doc: DocumentHistoryItem; 
  onSelect: (doc: DocumentHistoryItem) => void;
  onDelete: (doc: DocumentHistoryItem) => void;
  isSelecting: boolean;
  isDeleting: boolean;
}) {
  const dateStr = new Date(doc.created_at).toLocaleDateString("ko-KR", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <article
      className="relative rounded-lg border p-4 shadow-sm transition"
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
      {/* 삭제 버튼 */}
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDelete(doc);
        }}
        disabled={isDeleting || isSelecting}
        className="absolute top-3 right-3 p-1 text-gray-300 hover:text-red-500 transition-colors rounded-md hover:bg-red-50 disabled:opacity-30"
        title="삭제"
      >
        {isDeleting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <X className="h-3.5 w-3.5" />}
      </button>

      <div className="flex items-start gap-3">
        <div className="mt-0.5 rounded bg-blue-50 p-2 text-blue-600">
          <FileText className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1 pr-6">
          <h4
            className="truncate text-sm font-medium leading-snug"
            style={{ color: "#1A1C1E", fontFamily: "var(--font-public-sans)" }}
            title={doc.file_name}
          >
            {doc.file_name}
          </h4>
          <p
            className="mt-1 text-xs"
            style={{ color: "#74777F", fontFamily: "var(--font-public-sans)" }}
          >
            {dateStr}
          </p>
        </div>
      </div>
      
      <div className="mt-3 flex items-center gap-2">
        <button
          type="button"
          onClick={() => onSelect(doc)}
          disabled={isSelecting || isDeleting}
          className="inline-flex items-center gap-1 text-xs font-medium hover:underline disabled:opacity-50"
          style={{ color: "#002045", fontFamily: "var(--font-public-sans)" }}
        >
          {isSelecting ? "불러오는 중..." : "결과 보기"}
          {!isSelecting && <ChevronRight className="h-3.5 w-3.5" aria-hidden />}
        </button>
      </div>
    </article>
  );
}

export function RecentDocumentPanel() {
  const [docs, setDocs] = useState<DocumentHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [selectingId, setSelectingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    async function fetchHistory() {
      const clientId = localStorage.getItem("ade.client_id");
      if (!clientId) {
        setIsLoading(false);
        return;
      }

      try {
        const res = await fetch(`${API_BASE}/api/documents?client_id=${clientId}`);
        if (res.ok) {
          const data = await res.json();
          setDocs(data.documents);
        }
      } catch (err) {
        console.error("히스토리 로드 실패:", err);
      } finally {
        setIsLoading(false);
      }
    }

    fetchHistory();
  }, []);

  async function handleSelect(doc: DocumentHistoryItem) {
    const clientId = localStorage.getItem("ade.client_id");
    if (!clientId) return;

    setSelectingId(doc.doc_id);
    try {
      // 1. GCS에서 파싱된 데이터 가져오기
      const res = await fetch(`${API_BASE}/api/documents/${doc.doc_id}?client_id=${clientId}`);
      if (res.ok) {
        const contractData = await res.json();
        
        // 2. 세션 스토리지에 저장 (분석 페이지에서 사용하도록)
        sessionStorage.setItem("ade.analysis.docId", doc.doc_id);
        sessionStorage.setItem("ade.analysis.contract", JSON.stringify(contractData));
        sessionStorage.setItem("ade.analysis.fileName", doc.file_name);

        // 3. 분석 페이지로 이동
        window.location.href = "/analysis";
      } else {
        throw new Error("데이터 조회 실패");
      }
    } catch (err) {
      alert("문서 데이터를 불러오는 중 오류가 발생했습니다.");
      setSelectingId(null);
    }
  }

  async function handleDelete(doc: DocumentHistoryItem) {
    const clientId = localStorage.getItem("ade.client_id");
    if (!clientId) return;

    if (!confirm(`'${doc.file_name}' 분석 기록을 삭제하시겠습니까?\n이 작업은 되돌릴 수 없으며 실제 파일도 함께 삭제됩니다.`)) {
      return;
    }

    setDeletingId(doc.doc_id);
    try {
      const res = await fetch(`${API_BASE}/api/documents/${doc.doc_id}?client_id=${clientId}`, {
        method: "DELETE",
      });
      if (res.ok) {
        setDocs(prev => prev.filter(d => d.doc_id !== doc.doc_id));
      } else {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "삭제 실패");
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : "삭제 중 오류가 발생했습니다.");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <aside
      className="flex h-full min-h-0 w-full flex-col gap-4 overflow-y-auto lg:w-[320px] lg:shrink-0 lg:border-l lg:pl-6"
      style={{ borderColor: "#E2E8F0" }}
    >
      <h3
        className="text-base font-semibold"
        style={{ color: "#1A1C1E", fontFamily: "var(--font-public-sans)" }}
      >
        최근 분석 문서
      </h3>
      
      {isLoading ? (
        <div className="flex flex-1 items-center justify-center p-8">
          <Loader2 className="h-6 w-6 animate-spin text-gray-400" />
        </div>
      ) : docs.length > 0 ? (
        <ul className="flex flex-col gap-3 pb-8">
          {docs.map((doc) => (
            <li key={doc.doc_id}>
              <RecentDocumentCard 
                doc={doc} 
                onSelect={handleSelect} 
                onDelete={handleDelete}
                isSelecting={selectingId === doc.doc_id}
                isDeleting={deletingId === doc.doc_id}
              />
            </li>
          ))}
        </ul>
      ) : (
        <div 
          className="rounded-lg border border-dashed p-8 text-center text-sm"
          style={{ color: "#74777F", background: "#FAF9FD" }}
        >
          아직 분석한 문서가 없습니다.
        </div>
      )}
    </aside>
  );
}
