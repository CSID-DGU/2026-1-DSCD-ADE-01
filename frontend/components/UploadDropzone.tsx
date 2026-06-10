"use client";

import type { DragEvent } from "react";
import { useCallback, useRef, useState } from "react";
import { FileUp, Loader2 } from "lucide-react";

const MAX_BYTES = 20 * 1024 * 1024;
const ACCEPT =
  ".pdf,application/pdf";

type UploadDropzoneProps = {
  onFileSelect: (file: File) => void;
  isLoading?: boolean;
};

type Preview = { file: File; name: string; ext: string; sizeLabel: string };

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function isAllowedFile(file: File): boolean {
  const lower = file.name.toLowerCase();
  if (lower.endsWith(".pdf")) return true;
  const t = file.type;
  return t === "application/pdf";
}

export function UploadDropzone({ onFileSelect, isLoading }: UploadDropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const processFile = useCallback((file: File | undefined) => {
    if (!file) return;
    setError(null);
    if (!isAllowedFile(file)) {
      setError("PDF 파일만 업로드할 수 있습니다.");
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
    setPreview({ file, name: file.name, ext, sizeLabel: formatSize(file.size) });
  }, []);

  const preventDefaults = (e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    preventDefaults(e);
    setIsDragging(false);
    processFile(e.dataTransfer.files?.[0]);
  };

  const handleAnalyze = () => {
    if (preview && !isLoading) {
      onFileSelect(preview.file);
    }
  };

  return (
    <div
      className="flex flex-col items-center text-center"
      onDragEnter={(e) => { preventDefaults(e); setIsDragging(true); }}
      onDragOver={(e) => { preventDefaults(e); setIsDragging(true); }}
      onDragLeave={(e) => { preventDefaults(e); setIsDragging(false); }}
      onDrop={handleDrop}
    >
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="sr-only"
        aria-hidden
        tabIndex={-1}
        onChange={(e) => {
          processFile(e.target.files?.[0]);
          if (inputRef.current) inputRef.current.value = "";
        }}
      />

      {/* Icon */}
      <div
        className={`mb-4 flex h-14 w-14 items-center justify-center rounded-full transition-colors ${
          isDragging ? "bg-blue-light text-primary-navy" : "bg-panel-bg text-primary-navy"
        }`}
      >
        {isLoading ? (
          <Loader2 className="h-7 w-7 animate-spin" aria-hidden />
        ) : (
          <FileUp className="h-7 w-7" aria-hidden />
        )}
      </div>

      <h3
        className="text-lg font-semibold"
        style={{ color: "#1A1C1E", fontFamily: "var(--font-public-sans)" }}
      >
        파일을 여기에 놓거나 선택하세요
      </h3>
      <p
        className="mt-2 max-w-md text-sm"
        style={{ color: "#43474E", fontFamily: "var(--font-public-sans)" }}
      >
        드래그 앤 드롭 또는 파일 선택으로 계약서를 등록할 수 있습니다.
      </p>
      <p
        className="mt-2 text-xs"
        style={{ color: "#74777F", fontFamily: "var(--font-public-sans)" }}
      >
        지원 형식: PDF · 최대 용량: 20MB
      </p>

      {error && (
        <p className="mt-4 text-sm font-medium text-red-600" role="alert">
          {error}
        </p>
      )}

      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={isLoading}
        className="mt-8 inline-flex items-center justify-center rounded-lg px-6 py-2.5 text-sm font-medium text-white transition hover:opacity-90 disabled:opacity-50"
        style={{ background: "#002045", fontFamily: "var(--font-public-sans)" }}
      >
        파일 선택
      </button>

      {/* File preview card */}
      {preview && (
        <div
          className="mt-8 w-full max-w-md rounded-lg border px-4 py-3 text-left"
          style={{ background: "#FAF9FD", borderColor: "#E2E8F0" }}
        >
          <p
            className="text-xs font-medium"
            style={{ color: "#43474E", fontFamily: "var(--font-public-sans)" }}
          >
            선택된 파일
          </p>
          <p
            className="mt-1 truncate text-sm font-semibold"
            style={{ color: "#1A1C1E", fontFamily: "var(--font-public-sans)" }}
            title={preview.name}
          >
            {preview.name}
          </p>
          <dl
            className="mt-2 grid grid-cols-2 gap-2 text-xs"
            style={{ color: "#43474E", fontFamily: "var(--font-public-sans)" }}
          >
            <div>
              <dt className="font-medium" style={{ color: "#43474E" }}>확장자</dt>
              <dd style={{ color: "#1A1C1E" }}>{preview.ext}</dd>
            </div>
            <div>
              <dt className="font-medium" style={{ color: "#43474E" }}>파일 크기</dt>
              <dd style={{ color: "#1A1C1E" }}>{preview.sizeLabel}</dd>
            </div>
          </dl>
          {isLoading && (
            <p
              className="mt-3 flex items-center gap-2 text-xs font-medium"
              style={{ color: "#002045" }}
            >
              <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" aria-hidden />
              분석 중...
            </p>
          )}
          <button
            type="button"
            onClick={handleAnalyze}
            disabled={isLoading}
            className="mt-4 w-full rounded-lg border py-2.5 text-sm font-semibold transition hover:opacity-90 disabled:opacity-50"
            style={{
              borderColor: "#002045",
              background: "white",
              color: "#002045",
              fontFamily: "var(--font-public-sans)",
            }}
          >
            분석 시작
          </button>
        </div>
      )}
    </div>
  );
}
