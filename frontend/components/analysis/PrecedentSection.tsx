"use client";

import { useState } from "react";

export type FactCard = {
  label: string;
  text: string;
};

export type PrecedentItem = {
  title: string;
  tags: string[];
  facts: FactCard[];
  guide?: GuideItem[];
};

export type GuideItem = {
  id: string;
  text: string;
  checked: boolean;
};

function Tag({ label }: { label: string }) {
  return (
    <div
      className="flex items-center px-3 py-1 rounded-xl text-xs font-medium"
      style={{
        background: "#E9E7EB",
        border: "1px solid #C4C6CF",
        color: "#43474E",
        fontFamily: "var(--font-public-sans)",
        letterSpacing: "0.3px",
      }}
    >
      {label}
    </div>
  );
}

function FactItem({ fact }: { fact: FactCard }) {
  return (
    <div
      className="flex flex-col gap-[5px] p-3 rounded-lg w-full"
      style={{ background: "#FFFFFF", border: "1px solid #D9D9D9" }}
    >
      <div
        className="flex items-center justify-center px-3 py-0 self-start"
        style={{
          height: "24px",
          background: "#F3F5F8",
          border: "1px solid #D9DEE7",
        }}
      >
        <span
          className="text-sm font-semibold"
          style={{ color: "#1A1C1E", fontFamily: "var(--font-alexandria)" }}
        >
          {fact.label}
        </span>
      </div>
      <p
        className="text-sm px-[5px]"
        style={{ color: "#1A1C1E", fontFamily: "var(--font-public-sans)", lineHeight: "20px" }}
      >
        {fact.text}
      </p>
    </div>
  );
}

function GuideChecklist({ items }: { items: GuideItem[] }) {
  const [checked, setChecked] = useState<Record<string, boolean>>(
    Object.fromEntries(items.map((i) => [i.id, i.checked]))
  );

  return (
    <div
      className="flex flex-col gap-3 p-5 rounded"
      style={{ background: "#E0F2FE", border: "1px solid #9FCAFF" }}
    >
      <div className="flex flex-row items-center gap-2">
        <svg width="15" height="13" viewBox="0 0 15 13" fill="none">
          <path d="M1 7L5 11L14 2" stroke="#0061A5" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span
          className="text-xs font-medium uppercase tracking-[0.6px]"
          style={{ color: "#004172", fontFamily: "var(--font-alexandria)" }}
        >
          보완 가이드
        </span>
      </div>

      <div className="flex flex-col gap-2">
        {items.map((item) => {
          const isChecked = checked[item.id];
          return (
            <label key={item.id} className="flex flex-row items-center gap-3 cursor-pointer">
              <div className="shrink-0 flex items-center justify-center" style={{ width: "16px", height: "20px" }}>
                <div
                  className="flex items-center justify-center rounded-sm"
                  style={{
                    width: "16px",
                    height: "16px",
                    background: isChecked ? "#0061A5" : "#FFFFFF",
                    border: isChecked ? "none" : "1px solid #C4C6CF",
                    cursor: "pointer",
                  }}
                  onClick={() => setChecked((prev) => ({ ...prev, [item.id]: !isChecked }))}
                >
                  {isChecked && (
                    <svg width="10" height="8" viewBox="0 0 10 8" fill="none">
                      <path d="M1 4L3.5 6.5L9 1" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  )}
                </div>
              </div>
              <span
                className="text-sm"
                style={{
                  color: "#1A1C1E",
                  fontFamily: "var(--font-public-sans)",
                  lineHeight: "20px",
                  textDecoration: isChecked ? "line-through" : "none",
                  opacity: isChecked ? 0.7 : 1,
                }}
              >
                {item.text}
              </span>
            </label>
          );
        })}
      </div>
    </div>
  );
}

function CaseCard({ item }: { item: PrecedentItem }) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div
      className="flex flex-col rounded"
      style={{ background: "#FFFFFF", border: "1px solid #E2E8F0", boxShadow: "0px 1px 2px rgba(0,0,0,0.05)" }}
    >
      {/* Card header */}
      <div
        className="flex flex-row justify-between items-center px-5 py-5"
        style={{ background: "#F8FAFC", borderBottom: "1px solid #E2E8F0" }}
      >
        <h4
          className="text-lg font-semibold"
          style={{ color: "#1A365D", fontFamily: "var(--font-public-sans)" }}
        >
          {item.title}
        </h4>
        <button onClick={() => setExpanded((v) => !v)}>
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <rect width="18" height="18" rx="2" fill="#455F88" />
          </svg>
        </button>
      </div>

      {expanded && (
        <div className="flex flex-col gap-4 p-5">
          {/* Tags */}
          <div className="flex flex-row flex-wrap gap-2">
            {item.tags.map((tag) => (
              <Tag key={tag} label={tag} />
            ))}
          </div>

          {/* Fact cards */}
          {item.facts.map((fact, i) => (
            <FactItem key={i} fact={fact} />
          ))}

          {/* Guide checklist */}
          {item.guide && item.guide.length > 0 && (
            <div className="pt-4">
              <GuideChecklist items={item.guide} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function PrecedentSection({ precedents }: { precedents: PrecedentItem[] }) {
  return (
    <div className="flex flex-col gap-4">
      {/* Section header */}
      <div
        className="flex flex-row items-center gap-2 pb-2"
        style={{ borderBottom: "1px solid #C4C6CF" }}
      >
        <svg width="22" height="16" viewBox="0 0 22 16" fill="none">
          <rect width="22" height="16" rx="2" fill="#455F88" />
        </svg>
        <h3
          className="text-lg font-bold"
          style={{ color: "#002045", fontFamily: "var(--font-alexandria)" }}
        >
          관련 판례
        </h3>
      </div>

      <div className="flex flex-col gap-4">
        {precedents.map((item, i) => (
          <CaseCard key={i} item={item} />
        ))}
      </div>
    </div>
  );
}
