"use client";

import type { FormEvent } from "react";
import { useId, useState } from "react";
import { MessageCircle } from "lucide-react";

type ChatMessage = { id: string; role: "user" | "assistant"; text: string };

const EXAMPLE_QUESTIONS = [
  "보증금 있는 월세 계약에서 먼저 확인할 것은?",
  "특약에서 위험한 표현은 무엇인가요?",
  "전입신고와 확정일자는 왜 중요한가요?",
  "원상복구 특약은 어떻게 써야 하나요?",
] as const;

const MOCK_REPLY =
  "계약서를 업로드하면 해당 조항과 관련 법령·판례를 함께 검토해 더 정확한 답변을 제공할 수 있습니다.";

/**
 * 껍데기는 UploadWorkspaceShell이 담당합니다.
 */
export function UploadChatPanel() {
  const formId = useId();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const appendExchange = (userText: string) => {
    const trimmed = userText.trim();
    if (!trimmed) return;
    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      text: trimmed,
    };
    const botMsg: ChatMessage = {
      id: `a-${Date.now()}`,
      role: "assistant",
      text: MOCK_REPLY,
    };
    setMessages((prev) => [...prev, userMsg, botMsg]);
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    appendExchange(input);
    setInput("");
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="shrink-0 border-b border-border-default pb-4">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-panel-bg text-primary-navy">
            <MessageCircle className="h-5 w-5" aria-hidden />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-text-primary">계약 전 궁금한 점을 먼저 물어보세요</h2>
            <p className="mt-1 text-sm text-text-secondary">
              계약서를 업로드하기 전에도 임대차 계약 관련 기본 질문을 할 수 있습니다.
            </p>
          </div>
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          {EXAMPLE_QUESTIONS.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => setInput(q)}
              className="rounded-full border border-border-default bg-panel-bg px-3 py-1.5 text-left text-xs font-medium leading-snug text-text-primary transition hover:border-primary-navy/30 hover:bg-white"
            >
              {q}
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto py-4">
        {messages.length === 0 ? (
          <p className="text-center text-sm text-text-secondary">예시 질문을 입력창에 넣거나 직접 입력해 보세요.</p>
        ) : (
          <ul className="flex flex-col gap-3">
            {messages.map((m) => (
              <li
                key={m.id}
                className={`max-w-[95%] rounded-lg px-3 py-2 text-sm leading-relaxed ${
                  m.role === "user"
                    ? "ml-auto bg-primary-navy text-white"
                    : "mr-auto border border-border-default bg-panel-bg text-text-primary"
                }`}
              >
                {m.text}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="shrink-0 border-t border-border-default pt-3">
        <p className="mb-3 text-xs leading-relaxed text-text-secondary">
          계약서 업로드 후에는 해당 조항 기준으로 더 정확히 답변합니다.
        </p>
        <form id={formId} onSubmit={handleSubmit} className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <label className="sr-only" htmlFor={`${formId}-input`}>
            메시지 입력
          </label>
          <input
            id={`${formId}-input`}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="질문을 입력하세요…"
            className="min-h-[44px] min-w-0 flex-1 rounded-lg border border-border-default px-3 py-2 text-sm outline-none ring-primary-navy/20 focus:ring-2"
          />
          <button
            type="submit"
            className="shrink-0 rounded-lg bg-primary-navy px-4 py-2 text-sm font-medium text-white transition hover:bg-primary-navy/90"
          >
            보내기
          </button>
        </form>
      </div>
    </div>
  );
}
