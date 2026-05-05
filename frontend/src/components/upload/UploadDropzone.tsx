"use client";

import type { DragEvent } from "react";
import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { FileUp, Loader2 } from "lucide-react";

const MAX_BYTES = 20 * 1024 * 1024;
const ACCEPT =
  ".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document";

function isAllowedFile(file: File): boolean {
  const lower = file.name.toLowerCase();
  if (lower.endsWith(".pdf") || lower.endsWith(".docx")) return true;
  const t = file.type;
  return (
    t === "application/pdf" ||
    t === "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

type Preview = { name: string; ext: string; sizeLabel: string };

/**
 * 껍데기는 UploadWorkspaceShell이 담당합니다. 여기서는 본문·드롭존만 렌더링합니다.
 */
export function UploadDropzone() {
  const router = useRouter();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [progressLabel, setProgressLabel] = useState<string | null>(null);

  const processFile = useCallback((file: File | undefined) => {
    if (!file) return;
    setError(null);
    if (!isAllowedFile(file)) {
      setError("PDF 또는 DOCX 파일만 업로드할 수 있습니다.");
      setPreview(null);
      return;
    }
    if (file.size > MAX_BYTES) {
      setError("파일 크기는 20MB 이하여야 합니다.");
      setPreview(null);
      return;
    }
    const dot = file.name.lastIndexOf(".");
    const ext = dot >= 0 ? file.name.slice(dot + 1).toUpperCase() : "—";
    setPreview({
      name: file.name,
      ext,
      sizeLabel: formatSize(file.size),
    });
  }, []);

  const handleFileChange = () => {
    const file = fileInputRef.current?.files?.[0];
    processFile(file);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const triggerFileDialog = () => {
    fileInputRef.current?.click();
  };

  const preventDefaults = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    preventDefaults(e);
    const file = e.dataTransfer.files?.[0];
    processFile(file);
  };

  const runMockAnalysis = () => {
    if (!preview || busy) return;
    setBusy(true);
    const steps = [
      "파일 확인 중",
      "조항 추출 중",
      "관련 법령·판례 검색 중",
      "분석 결과 생성 중",
    ] as const;
    let i = 0;
    const tick = () => {
      if (i < steps.length) {
        setProgressLabel(steps[i]);
        i += 1;
        window.setTimeout(tick, 340);
      } else {
        router.push("/contract-analysis");
      }
    };
    tick();
  };

  return (
    <div
      onDragEnter={preventDefaults}
      onDragOver={preventDefaults}
      onDragLeave={preventDefaults}
      onDrop={handleDrop}
      className="flex min-h-0 flex-1 flex-col"
    >
      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPT}
        className="sr-only"
        aria-hidden
        tabIndex={-1}
        onChange={handleFileChange}
      />
      <div className="flex flex-1 flex-col items-center text-center">
        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-panel-bg text-primary-navy">
          {busy ? (
            <Loader2 className="h-7 w-7 animate-spin" aria-hidden />
          ) : (
            <FileUp className="h-7 w-7" aria-hidden />
          )}
        </div>
        <h3 className="text-lg font-semibold text-text-primary">파일을 여기에 놓거나 선택하세요</h3>
        <p className="mt-2 max-w-md text-sm text-text-secondary">
          드래그 앤 드롭 또는 파일 선택으로 계약서를 등록할 수 있습니다.
        </p>
        <p className="mt-3 text-xs text-text-secondary">지원 형식: PDF, DOCX · 최대 용량: 20MB</p>
        {error ? (
          <p className="mt-4 max-w-md text-sm font-medium text-warning-text" role="alert">
            {error}
          </p>
        ) : null}
        <button
          type="button"
          onClick={triggerFileDialog}
          disabled={busy}
          className="mt-8 inline-flex items-center justify-center rounded-lg bg-primary-navy px-6 py-2.5 text-sm font-medium text-white transition hover:bg-primary-navy/90 disabled:opacity-50"
        >
          파일 선택
        </button>

        {preview ? (
          <div className="mt-8 w-full max-w-md rounded-lg border border-border-default bg-panel-bg px-4 py-3 text-left">
            <p className="text-xs font-medium text-text-secondary">선택된 파일</p>
            <p className="mt-1 truncate text-sm font-semibold text-text-primary" title={preview.name}>
              {preview.name}
            </p>
            <dl className="mt-2 grid grid-cols-2 gap-2 text-xs text-text-secondary">
              <div>
                <dt className="font-medium text-text-secondary/90">확장자</dt>
                <dd className="text-text-primary">{preview.ext}</dd>
              </div>
              <div>
                <dt className="font-medium text-text-secondary/90">용량(표시)</dt>
                <dd className="text-text-primary">{preview.sizeLabel}</dd>
              </div>
            </dl>
            {progressLabel ? (
              <p className="mt-3 flex items-center gap-2 text-xs font-medium text-primary-navy">
                <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" aria-hidden />
                {progressLabel}
              </p>
            ) : null}
            <button
              type="button"
              onClick={runMockAnalysis}
              disabled={busy}
              className="mt-4 w-full rounded-lg border border-primary-navy bg-white py-2.5 text-sm font-semibold text-primary-navy transition hover:bg-page-bg disabled:opacity-50"
            >
              분석 시작
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
