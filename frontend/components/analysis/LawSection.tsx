"use client";

export type LawItem = {
  rank: number;
  name: string;
  warning?: string;
  detail?: string;
};

function NumberBadge({ n }: { n: number }) {
  return (
    <div
      className="flex items-center justify-center shrink-0 rounded-sm text-xs font-medium"
      style={{ width: "24px", height: "24px", background: "#D6E3FF", color: "#001B3C", fontFamily: "var(--font-alexandria)" }}
    >
      {n}
    </div>
  );
}

function LawCard({ item }: { item: LawItem }) {
  return (
    <div
      className="flex flex-col gap-[10px] p-3 rounded"
      style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", boxShadow: "0px 1px 2px rgba(0,0,0,0.05)" }}
    >
      {/* Law name row */}
      <div className="flex flex-row items-center gap-[10px]">
        <NumberBadge n={item.rank} />
        <p
          className="text-sm font-semibold"
          style={{ color: "#002045", fontFamily: "var(--font-public-sans)", lineHeight: "22px" }}
        >
          {item.name}
        </p>
      </div>

      {/* Warning banner */}
      {item.warning && (
        <div className="flex flex-col gap-[5px] pl-9">
          <div
            className="flex flex-row items-center gap-3 p-3 rounded-sm"
            style={{ background: "#FEE2E2", border: "1px solid #F65746" }}
          >
            <svg width="22" height="19" viewBox="0 0 22 19" fill="none" className="shrink-0">
              <path d="M11 1L21 18H1L11 1Z" fill="#EF4444" />
              <rect x="10" y="7" width="2" height="6" rx="1" fill="white" />
              <rect x="10" y="14" width="2" height="2" rx="1" fill="white" />
            </svg>
            <p
              className="text-[15px] font-medium"
              style={{ color: "#991B1B", fontFamily: "var(--font-alexandria)" }}
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
