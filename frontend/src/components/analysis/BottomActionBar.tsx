"use client";

import { Share2, MessageCircle } from "lucide-react";
import { openChatbotPanel } from "@/lib/chatbotEvents";

export function BottomActionBar() {
  return (
    <div className="shrink-0 border-t border-border-default bg-panel-bg px-4 py-3 sm:px-6">
      <div className="flex flex-wrap gap-2 sm:gap-3">
        <button
          type="button"
          className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg border border-border-default bg-white px-4 py-2.5 text-sm font-medium text-text-primary transition hover:bg-page-bg sm:flex-none"
        >
          <Share2 className="h-4 w-4" aria-hidden />
          공유하기
        </button>
        <button
          type="button"
          className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-primary-navy px-4 py-2.5 text-sm font-medium text-white transition hover:bg-primary-navy/90 sm:flex-none"
          onClick={() => openChatbotPanel()}
        >
          <MessageCircle className="h-4 w-4" aria-hidden />
          챗봇에게 질문하기
        </button>
      </div>
    </div>
  );
}
