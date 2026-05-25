"use client";

import { useState } from "react";
import { TopNavBar } from "@/components/TopNavBar";
import type { NavTab } from "@/components/TopNavBar";
import { UploadDropzone } from "@/components/UploadDropzone";
import { RecentDocumentPanel } from "@/components/RecentDocumentPanel";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

export default function UploadPage() {
  const [fileName, setFileName] = useState<string>();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [activeTab, setActiveTab] = useState<NavTab>("analysis");

  async function handleFileSelect(file: File) {
    setFileName(file.name);
    setIsLoading(true);
    setError(undefined);

    try {
      const form = new FormData();
      form.append("file", file);

      const res = await fetch(`${API_BASE}/v1/contracts/analyze/sync`, {
        method: "POST",
        body: form,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail ?? `오류 ${res.status}`);
      }

      const data = await res.json();
      sessionStorage.setItem("ade.analysis.result", JSON.stringify(data));
      sessionStorage.setItem("ade.analysis.fileName", file.name);

      window.location.href = "/analysis";
    } catch (e) {
      setError(e instanceof Error ? e.message : "알 수 없는 오류가 발생했습니다.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col" style={{ background: "#F4F3F7" }}>
      <TopNavBar
        fileName={fileName}
        mode="upload"
        activeTab={activeTab}
        onTabChange={setActiveTab}
      />

      <main
        className="flex min-h-0 flex-1 flex-col gap-8 px-4 py-6 sm:px-6 lg:flex-row lg:items-stretch lg:gap-0 lg:px-6"
      >
        {/* Left: upload area */}
        <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-6 overflow-y-auto lg:min-h-0 lg:flex-1 lg:pr-8">
          {activeTab === "analysis" ? (
            <div>
              <h1
                className="text-xl font-bold sm:text-2xl"
                style={{ color: "#1A1C1E", fontFamily: "var(--font-public-sans)" }}
              >
                임대차 계약서 AI 분석 서비스
              </h1>
              <p
                className="mt-2 text-sm"
                style={{ color: "#43474E", fontFamily: "var(--font-public-sans)" }}
              >
                PDF 또는 DOCX를 업로드하면 조항 추출과 위험 검토를 시작합니다.
              </p>
            </div>
          ) : (
            <div>
              <h1
                className="text-xl font-bold sm:text-2xl"
                style={{ color: "#1A1C1E", fontFamily: "var(--font-public-sans)" }}
              >
                계약 전 상담
              </h1>
              <p
                className="mt-2 text-sm"
                style={{ color: "#43474E", fontFamily: "var(--font-public-sans)" }}
              >
                업로드 전에도 임대차 관련 기본 질문을 할 수 있습니다.
              </p>
            </div>
          )}

          {/* Workspace shell */}
          <div className="flex min-h-[520px] w-full min-w-0 flex-1 flex-col">
            <div
              className="flex min-h-0 flex-1 flex-col rounded-xl border border-dashed p-8 shadow-sm sm:p-10"
              style={{ background: "white", borderColor: "#E2E8F0" }}
            >
              <div className="flex min-h-0 flex-1 flex-col">
                {activeTab === "analysis" ? (
                  <UploadDropzone onFileSelect={handleFileSelect} isLoading={isLoading} />
                ) : (
                  <div
                    className="flex flex-1 items-center justify-center text-sm"
                    style={{ color: "#74777F", fontFamily: "var(--font-public-sans)" }}
                  >
                    챗봇 기능은 준비 중입니다.
                  </div>
                )}
              </div>
            </div>
          </div>

          {error && (
            <p className="text-sm text-red-600">{error}</p>
          )}
        </div>

        {/* Right: recent documents */}
        <RecentDocumentPanel />
      </main>
    </div>
  );
}
