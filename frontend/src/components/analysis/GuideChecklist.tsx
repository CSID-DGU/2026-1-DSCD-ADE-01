"use client";

import { useEffect, useState } from "react";
import type { GuideItem } from "@/types/contract";
import { openChatbotPanel } from "@/lib/chatbotEvents";

function cloneItems(items: GuideItem[]): GuideItem[] {
  return items.map((g) => ({ ...g, checked: g.checked ?? false }));
}

function downloadTxt(filename: string, lines: GuideItem[]) {
  const body = lines.map((g) => `${g.checked ? "[x]" : "[ ]"} ${g.text}`).join("\n");
  const blob = new Blob([body], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

type GuideChecklistProps = {
  items: GuideItem[];
  showCardHeading?: boolean;
  clauseId: string;
  clauseLabel: string;
  clauseSourcePath: string;
};

export function GuideChecklist({
  items,
  showCardHeading = true,
  clauseId,
  clauseLabel,
  clauseSourcePath,
}: GuideChecklistProps) {
  const [local, setLocal] = useState<GuideItem[]>(() => cloneItems(items));
  const [revision, setRevision] = useState<string | null>(null);

  useEffect(() => {
    setLocal(cloneItems(items));
    setRevision(null);
  }, [clauseId, clauseSourcePath, items]);

  if (local.length === 0) return null;

  const askClause = () => {
    openChatbotPanel({
      initialMessage: `${clauseLabel} 조항의 보완 가이드를 바탕으로 추가로 확인할 점을 알려줘.`,
      context: {
        clauseId,
        clauseLabel,
        clauseSourcePath,
        source: "guide",
      },
    });
  };

  const handleDownload = () => {
    const safe = clauseLabel.replace(/\s+/g, "_").slice(0, 40);
    downloadTxt(`보완가이드_${safe}.txt`, local);
  };

  const handleRevision = () => {
    setRevision(
      "수정 제안: 임차인의 원상복구 범위는 입주 당시 상태와 통상 마모를 제외한 손상 범위로 한정하며, 구체 항목은 별도 체크리스트에 따른다.",
    );
  };

  return (
    <section className="rounded-lg border border-guide-border bg-guide-bg p-3.5">
      {showCardHeading ? (
        <h4 className="text-sm font-semibold text-primary-navy">보완 가이드</h4>
      ) : null}
      <ul className={`${showCardHeading ? "mt-3" : ""} space-y-2 text-sm leading-relaxed text-text-secondary`}>
        {local.map((g) => (
          <li key={g.id} className="flex gap-2">
            <button
              type="button"
              role="checkbox"
              aria-checked={Boolean(g.checked)}
              aria-label={g.checked ? "체크 해제" : "체크"}
              onClick={() =>
                setLocal((prev) =>
                  prev.map((x) => (x.id === g.id ? { ...x, checked: !x.checked } : x)),
                )
              }
              className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border border-border-default text-[10px] font-bold leading-none transition ${
                g.checked
                  ? "border-primary-navy bg-primary-navy text-white"
                  : "bg-white text-transparent"
              }`}
            >
              ✓
            </button>
            <span className="min-w-0 whitespace-pre-wrap">{g.text}</span>
          </li>
        ))}
      </ul>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleDownload}
          className="rounded-md border border-border-default bg-white px-2.5 py-1 text-xs font-medium text-text-primary transition hover:bg-page-bg"
        >
          체크리스트 다운로드
        </button>
        <button
          type="button"
          onClick={askClause}
          className="rounded-md border border-border-default bg-white px-2.5 py-1 text-xs font-medium text-text-primary transition hover:bg-page-bg"
        >
          챗봇에게 이 조항 질문하기
        </button>
        <button
          type="button"
          onClick={handleRevision}
          className="rounded-md border border-border-default bg-white px-2.5 py-1 text-xs font-medium text-text-primary transition hover:bg-page-bg"
        >
          수정 문구 생성
        </button>
      </div>
      {revision ? (
        <div className="mt-3 rounded-lg border border-primary-navy/25 bg-white px-3 py-2.5 text-sm leading-relaxed text-text-primary shadow-sm">
          {revision}
        </div>
      ) : null}
    </section>
  );
}
