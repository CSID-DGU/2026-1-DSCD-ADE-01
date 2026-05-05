import type { ReactNode } from "react";

type AnalysisInfoBoxProps = {
  title: string;
  children: ReactNode;
};

export function AnalysisInfoBox({ title, children }: AnalysisInfoBoxProps) {
  return (
    <section className="rounded-lg border border-border-default bg-white p-4 shadow-sm">
      <span className="inline-flex rounded-md border border-[#D9DEE7] bg-[#F3F5F8] px-3 py-1 text-sm font-semibold text-text-primary">
        {title}
      </span>
      <div className="mt-3 whitespace-pre-wrap text-sm leading-relaxed text-text-secondary">
        {children}
      </div>
    </section>
  );
}
