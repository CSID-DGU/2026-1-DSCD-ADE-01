"use client";

export type LawItem = {
  rank: number;
  name: string;
  warning?: string;
  detail?: string;
  isViolation?: boolean;
};

function NumberBadge({ n, isViolation }: { n: number; isViolation?: boolean }) {
  return (
    <div
      className="flex items-center justify-center shrink-0 rounded-sm text-xs font-medium"
      style={{ 
        width: "24px", 
        height: "24px", 
        background: isViolation ? "#FEE2E2" : "#D6E3FF", 
        color: isViolation ? "#991B1B" : "#001B3C", 
        fontFamily: "var(--font-alexandria)" 
      }}
    >
      {n}
    </div>
  );
}

function LawCard({ item }: { item: LawItem }) {
  const isViolation = item.isViolation || !!item.warning;

  return (
    <div
      className="flex flex-col gap-[10px] p-4 rounded-lg transition-all"
      style={{ 
        background: "#FFFFFF", 
        border: isViolation ? "1.5px solid #F65746" : "1px solid #E2E8F0", 
        boxShadow: isViolation ? "0px 4px 6px -1px rgba(246, 87, 70, 0.1)" : "0px 1px 2px rgba(0,0,0,0.05)" 
      }}
    >
      {/* Law name row */}
      <div className="flex flex-row items-center gap-[10px] flex-wrap">
        <NumberBadge n={item.rank} isViolation={isViolation} />
        <p
          className="text-sm font-bold"
          style={{ color: isViolation ? "#DC2626" : "#002045", fontFamily: "var(--font-public-sans)", lineHeight: "22px" }}
        >
          {item.name}
        </p>
        {isViolation && (
          <span className="px-2 py-0.5 rounded bg-red-600 text-[10px] font-black text-white uppercase tracking-tighter animate-pulse">
            주의
          </span>
        )}
      </div>

      {/* Warning banner */}
      {item.warning && (
        <div className="flex flex-col gap-[5px] pl-9">
          <div
            className="flex flex-row items-start gap-3 p-3 rounded-md"
            style={{ background: "#FEF2F2", border: "1px solid #FEE2E2" }}
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" className="shrink-0 mt-0.5">
              <path d="M12 9V14M12 17.01L12.01 16.998M12 21C16.9706 21 21 16.9706 21 12C21 7.02944 16.9706 3 12 3C7.02944 3 3 7.02944 3 12C3 16.9706 7.02944 21 12 21Z" stroke="#EF4444" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
            <p
              className="text-sm font-semibold leading-relaxed"
              style={{ color: "#991B1B", fontFamily: "var(--font-public-sans)" }}
            >
              {item.warning}
            </p>
          </div>
        </div>
      )}

      {/* Detail (Law Content) - Always Visible */}
      {item.detail && (
        <div className="pl-9">
          <div
            className="px-4 py-3 rounded-md"
            style={{ 
              background: "#F8FAFC", 
              borderLeft: `4px solid ${item.warning ? "#F65746" : "#455F88"}`,
              boxShadow: "inset 0 1px 2px rgba(0,0,0,0.02)"
            }}
          >
            <p
              className="text-sm whitespace-pre-wrap"
              style={{ color: "#334155", fontFamily: "var(--font-public-sans)", lineHeight: "1.6" }}
            >
              {item.detail}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

export function LawSection({ laws }: { laws: LawItem[] }) {
  return (
    <div className="flex flex-col gap-4">
      {/* Section header */}
      <div
        className="flex flex-row items-center gap-2 pb-2"
        style={{ borderBottom: "1px solid #C4C6CF" }}
      >
        <svg width="18" height="19" viewBox="0 0 18 19" fill="none">
          <rect width="18" height="19" rx="2" fill="#455F88" />
        </svg>
        <h3
          className="text-lg font-bold"
          style={{ color: "#002045", fontFamily: "var(--font-alexandria)" }}
        >
          관련 법령
        </h3>
      </div>

      {/* Cards */}
      <div className="flex flex-col gap-3">
        {laws.map((item) => (
          <LawCard key={item.rank} item={item} />
        ))}
      </div>
    </div>
  );
}
