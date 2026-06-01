"use client";

type GeneralTerm = {
  title: string;
  text: string;
};

type DocumentPanelProps = {
  contractTitle?: string;
  specialTerms: string[];
  generalTerms: GeneralTerm[];
  onTermClick?: (index: number) => void;
};

export function DocumentPanel({ 
  contractTitle, 
  specialTerms, 
  generalTerms,
  onTermClick 
}: DocumentPanelProps) {
  return (
    <section
      className="flex flex-col overflow-y-auto"
      style={{
        width: "640px",
        background: "#FFFFFF",
        borderRight: "1px solid #C4C6CF",
        padding: "32px 32px 128px",
        flexShrink: 0,
      }}
    >
      {/* Document title */}
      <div
        className="flex flex-col items-center gap-[8px] pb-6"
        style={{ borderBottom: "1px solid #E2E8F0" }}
      >
        <h2
          className="text-lg font-semibold text-center"
          style={{
            color: "#1A1C1E",
            fontFamily: "var(--font-public-sans)",
            letterSpacing: "1.8px",
            textTransform: "uppercase",
          }}
        >
          {contractTitle ?? "표준 주택임대차계약서"}
        </h2>
        <p
          className="text-sm text-center"
          style={{ color: "#43474E", fontFamily: "var(--font-public-sans)" }}
        >
          Standard Residential Lease Agreement
        </p>
      </div>

      <div className="flex flex-col gap-8 py-6">
        {/* 1. 특약 사항 섹션 (최상단) */}
        {specialTerms.length > 0 && (
          <div className="flex flex-col gap-4">
            <h3 className="px-2 text-sm font-black text-blue-700 uppercase tracking-widest border-l-4 border-blue-600">
              특약 사항
            </h3>
            <div className="flex flex-col gap-2">
              {specialTerms.map((text, i) => (
                <button
                  key={i}
                  onClick={() => onTermClick?.(i)}
                  className="group flex flex-col gap-1 rounded-lg border border-gray-200 bg-gray-50 p-4 text-left transition hover:border-blue-300 hover:bg-blue-50 hover:shadow-sm"
                >
                  <span className="text-[10px] font-bold text-gray-400 uppercase group-hover:text-blue-500">특약 {i + 1}</span>
                  <p className="text-sm text-gray-800 leading-relaxed font-medium">
                    {text}
                  </p>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* 구분선 */}
        <div className="h-px bg-gray-100 mx-2" />

        {/* 2. 일반 조항 섹션 */}
        {generalTerms.length > 0 && (
          <div className="flex flex-col gap-4">
            <h3 className="px-2 text-sm font-black text-gray-500 uppercase tracking-widest border-l-4 border-gray-300">
              일반 조항
            </h3>
            <div className="flex flex-col gap-4">
              {generalTerms.map((term, i) => (
                <div key={i} className="flex flex-col gap-1 px-2">
                  <p className="text-xs font-bold text-gray-500">{term.title}</p>
                  <div className="p-3 border rounded bg-white border-gray-100">
                    <p className="text-xs text-gray-600 leading-relaxed">
                      {term.text}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
