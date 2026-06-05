"use client";

import React, { useState, useRef, useEffect } from "react";
import { MessageCircle, X, Send, Loader2, Bot, User } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

type Message = {
  role: "user" | "assistant";
  content: string;
  sources?: any[];
};

type ChatBotProps = {
  isOpen: boolean;
  onOpen: () => void;
  onClose: () => void;
  context: {
    report: any;
    clauses: any;
    rawContract?: any;
  };
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export function ChatBot({ isOpen, onOpen, onClose, context }: ChatBotProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: "안녕하세요! 분석된 계약서에 대해 궁금한 점이 있으신가요? 무엇이든 물어보세요.",
    },
  ]);
  const [inputValue, setInputValue] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
    }
  }, [messages, isOpen]);

  const handleSendMessage = async () => {
    if (!inputValue.trim() || isLoading) return;

    const userMessage = inputValue.trim();
    setInputValue("");
    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: [...messages, { role: "user", content: userMessage }].map(m => ({
            role: m.role,
            content: m.content
          })),
          context: context,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: "Chat API failed" }));
        throw new Error(errorData.detail || "Chat API failed");
      }

      const data = await response.json();
      setMessages((prev) => [...prev, { 
        role: "assistant", 
        content: data.answer,
        sources: data.sources
      }]);
    } catch (error: any) {
      console.error("Chat error:", error);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `죄송합니다. 오류가 발생했습니다: ${error.message}` },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <>
      {/* Floating FAB Button */}
      {!isOpen && (
        <button
          onClick={onOpen}
          className="fixed bottom-8 right-8 z-50 flex items-center justify-center w-14 h-14 bg-[#002045] text-white rounded-full shadow-2xl hover:bg-[#003366] transition-all transform hover:scale-110"
        >
          <MessageCircle className="w-7 h-7" />
        </button>
      )}

      {/* Chat Window */}
      {isOpen && (
        <div className="fixed bottom-8 right-8 z-[100] w-[600px] h-[700px] bg-white rounded-2xl shadow-[0_20px_50px_rgba(0,0,0,0.2)] border border-gray-200 flex flex-col overflow-hidden animate-in slide-in-from-bottom-5 duration-300">
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 bg-[#002045] text-white">
            <div className="flex items-center gap-2">
              <Bot className="w-5 h-5" />
              <span className="font-bold text-lg">ADE AI 챗봇</span>
            </div>
            <button
              onClick={onClose}
              className="p-1 hover:bg-white/10 rounded-full transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4 bg-gray-50">
            {messages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`flex gap-2 max-w-[85%] ${
                    msg.role === "user" ? "flex-row-reverse" : "flex-row"
                  }`}
                >
                  <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
                    msg.role === "user" ? "bg-blue-100 text-blue-600" : "bg-gray-200 text-gray-600"
                  }`}>
                    {msg.role === "user" ? <User className="w-5 h-5" /> : <Bot className="w-5 h-5" />}
                  </div>
                  <div
                    className={`px-4 py-2 rounded-2xl text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "bg-[#002045] text-white rounded-tr-none"
                        : "bg-white border border-gray-200 text-gray-800 rounded-tl-none shadow-sm"
                    }`}
                  >
                    <div className={msg.role === "assistant" ? "prose prose-sm max-w-none prose-p:leading-relaxed prose-headings:mb-2 prose-headings:mt-4 first:prose-headings:mt-0" : ""}>
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                    </div>
                    
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="mt-2 pt-2 border-t border-gray-100 flex flex-col gap-1">
                        <p className="text-[10px] font-bold text-blue-600 flex items-center gap-1">
                          <Bot className="w-3 h-3" />
                          검색 결과 참고됨:
                        </p>
                        <div className="flex flex-wrap gap-1">
                          {msg.sources.map((s: any, sIdx: number) => (
                            <span key={sIdx} title={s.content} className="text-[9px] bg-blue-50 text-blue-700 px-1.5 py-0.5 rounded border border-blue-100 cursor-help">
                              {s.title || "검색 결과"}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="flex gap-2 items-center px-4 py-2 bg-white border border-gray-100 rounded-2xl rounded-tl-none shadow-sm">
                  <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
                  <span className="text-xs text-gray-500 font-medium">생각 중...</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="p-4 bg-white border-t border-gray-100">
            <div className="relative flex items-center">
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyPress={(e) => e.key === "Enter" && handleSendMessage()}
                placeholder="질문을 입력하세요..."
                className="w-full pl-4 pr-12 py-3 bg-gray-100 border-none rounded-xl text-sm focus:ring-2 focus:ring-[#002045] transition-all"
              />
              <button
                onClick={handleSendMessage}
                disabled={!inputValue.trim() || isLoading}
                className="absolute right-2 p-2 text-[#002045] hover:bg-[#002045] hover:text-white rounded-lg disabled:opacity-30 disabled:hover:bg-transparent disabled:hover:text-[#002045] transition-all"
              >
                <Send className="w-5 h-5" />
              </button>
            </div>
            <p className="mt-2 text-[10px] text-gray-400 text-center">
              AI는 실수를 할 수 있습니다. 중요한 내용은 반드시 전문가와 상담하세요.
            </p>
          </div>
        </div>
      )}
    </>
  );
}
