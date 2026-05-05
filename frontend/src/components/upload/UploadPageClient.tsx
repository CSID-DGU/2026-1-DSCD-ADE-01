"use client";

import { useState } from "react";
import type { HeaderTab } from "@/components/Header";
import { Header } from "@/components/Header";
import { UploadDropzone } from "@/components/upload/UploadDropzone";
import { UploadChatPanel } from "@/components/upload/UploadChatPanel";
import { UploadWorkspaceShell } from "@/components/upload/UploadWorkspaceShell";
import { RecentDocumentPanel } from "@/components/upload/RecentDocumentPanel";
import type { RecentDocument } from "@/types/contract";

export function UploadPageClient({ documents }: { documents: RecentDocument[] }) {
  const [activeTab, setActiveTab] = useState<HeaderTab>("analysis");

  return (
    <div className="flex min-h-screen flex-col bg-page-bg">
      <Header context="upload" activeTab={activeTab} onTabChange={setActiveTab} />
      <main className="flex min-h-0 flex-1 flex-col gap-8 px-4 py-6 sm:px-6 lg:flex-row lg:items-stretch lg:gap-0 lg:px-6">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-6 overflow-y-auto lg:min-h-0 lg:flex-1 lg:pr-8">
          {activeTab === "analysis" ? (
            <div>
              <h1 className="text-xl font-bold text-text-primary sm:text-2xl">
                임대차 계약서 AI 분석 서비스
              </h1>
              <p className="mt-2 text-sm text-text-secondary">
                PDF 또는 DOCX를 업로드하면 조항 추출과 위험 검토를 시작합니다.
              </p>
            </div>
          ) : (
            <div>
              <h1 className="text-xl font-bold text-text-primary sm:text-2xl">계약 전 상담</h1>
              <p className="mt-2 text-sm text-text-secondary">
                업로드 전에도 임대차 관련 기본 질문을 할 수 있습니다.
              </p>
            </div>
          )}

          <UploadWorkspaceShell>
            {activeTab === "analysis" ? <UploadDropzone /> : <UploadChatPanel />}
          </UploadWorkspaceShell>
        </div>
        <RecentDocumentPanel documents={documents} />
      </main>
    </div>
  );
}
