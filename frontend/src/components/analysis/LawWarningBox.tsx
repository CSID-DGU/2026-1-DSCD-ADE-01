import type { LawWarning } from "@/types/contract";
import { AlertTriangle } from "lucide-react";

type LawWarningBoxProps = {
  warning: LawWarning;
};

export function LawWarningBox({ warning }: LawWarningBoxProps) {
  const levelColors: Record<LawWarning["level"], string> = {
    주의: "border-amber-500/60 bg-amber-50 text-amber-950",
    위험: "border-warning-border bg-warning-bg text-warning-text",
    위법가능: "border-warning-border bg-warning-bg text-warning-text",
  };

  const cls = levelColors[warning.level] ?? levelColors["위험"];

  return (
    <aside
      className={`mt-3 rounded-lg border px-3 py-2.5 text-sm shadow-sm ${cls}`}
      role="alert"
    >
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 opacity-90" aria-hidden />
        <div className="min-w-0">
          <p className="font-semibold">
            [{warning.level}] {warning.title}
          </p>
          <p className="mt-1.5 whitespace-pre-wrap leading-relaxed opacity-95">
            사유: {warning.reason}
          </p>
        </div>
      </div>
    </aside>
  );
}
