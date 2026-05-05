"use client";

import { X } from "lucide-react";

type TextDetailModalProps = {
  open: boolean;
  title: string;
  body: string;
  onClose: () => void;
};

export function TextDetailModal({ open, title, body, onClose }: TextDetailModalProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="text-detail-title"
      onClick={onClose}
    >
      <div
        className="flex max-h-[min(85vh,720px)] w-full max-w-lg flex-col rounded-xl border border-border-default bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between border-b border-border-default px-4 py-3">
          <h2 id="text-detail-title" className="pr-2 text-sm font-semibold text-text-primary">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-text-secondary hover:bg-page-bg"
            aria-label="닫기"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed text-text-primary">{body}</pre>
        </div>
      </div>
    </div>
  );
}
