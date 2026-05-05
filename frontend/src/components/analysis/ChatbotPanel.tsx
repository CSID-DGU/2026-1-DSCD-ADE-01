"use client";

import type { FormEvent } from "react";
import { useCallback, useEffect, useState } from "react";
import { X } from "lucide-react";
import type { ChatbotOpenDetail } from "@/types/contract";
import { CHATBOT_OPEN_EVENT } from "@/lib/chatbotEvents";

type ChatMessage = { id: string; role: "user" | "assistant"; text: string };

const MOCK_REPLY =
  "데모 응답입니다. 계약서를 업로드하면 조항·법령·판례 컨텍스트를 반영한 답변으로 확장할 수 있습니다.";

export function ChatbotPanel() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);

  const applyOpenDetail = useCallback((detail?: ChatbotOpenDetail) => {
    setOpen(true);
    const msg = detail?.initialMessage?.trim();
    if (msg) setInput(msg);
    else setInput("");
  }, []);

  useEffect(() => {
    const handler = (e: Event) => {
      const ce = e as CustomEvent<ChatbotOpenDetail | undefined>;
      applyOpenDetail(ce.detail);
    };
    window.addEventListener(CHATBOT_OPEN_EVENT, handler);
    return () => window.removeEventListener(CHATBOT_OPEN_EVENT, handler);
  }, [applyOpenDetail]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed) return;
    const userMsg: ChatMessage = { id: `u-${Date.now()}`, role: "user", text: trimmed };
    const botMsg: ChatMessage = { id: `a-${Date.now()}`, role: "assistant", text: MOCK_REPLY };
    setMessages((prev) => [...prev, userMsg, botMsg]);
    setInput("");
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end bg-black/30 p-4 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="chatbot-title"
      onClick={() => setOpen(false)}
    >
      <div
        className="mt-auto flex h-[min(480px,75vh)] w-full max-w-md flex-col rounded-xl border border-border-default bg-white shadow-xl"
        onClick={(ev) => ev.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-border-default px-4 py-3">
          <h2 id="chatbot-title" className="text-sm font-semibold text-text-primary">
            챗봇
          </h2>
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="rounded p-1 text-text-secondary hover:bg-page-bg"
            aria-label="닫기"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-4 py-3">
          {messages.length === 0 ? (
            <p className="text-sm text-text-secondary">선택한 조항과 관련해 질문해 보세요. (데모)</p>
          ) : (
            <ul className="flex flex-col gap-2">
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

        <form
          onSubmit={handleSubmit}
          className="shrink-0 border-t border-border-default p-4"
        >
          <div className="flex gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="메시지 입력..."
              className="min-w-0 flex-1 rounded-lg border border-border-default px-3 py-2 text-sm outline-none ring-primary-navy/20 focus:ring-2"
            />
            <button
              type="submit"
              className="rounded-lg bg-primary-navy px-4 py-2 text-sm font-medium text-white transition hover:bg-primary-navy/90"
            >
              전송
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
