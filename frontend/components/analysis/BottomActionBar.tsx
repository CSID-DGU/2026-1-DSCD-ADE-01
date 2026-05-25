"use client";

type BottomActionBarProps = {
  onShare?: () => void;
  onChatbot?: () => void;
};

export function BottomActionBar({ onShare, onChatbot }: BottomActionBarProps) {
  return (
    <div
      className="fixed bottom-0 left-0 right-0 flex flex-row justify-end items-center gap-3 px-4 py-4"
      style={{
        background: "#FFFFFF",
        borderTop: "1px solid #C4C6CF",
        boxShadow: "0px -4px 6px -1px rgba(0,0,0,0.05)",
        zIndex: 10,
        height: "75px",
      }}
    >
      <button
        className="flex items-center justify-center px-5 py-[10px] rounded text-sm font-semibold"
        style={{
          border: "1px solid #74777F",
          color: "#002045",
          fontFamily: "var(--font-alexandria)",
          height: "42px",
        }}
        onClick={onShare}
      >
        공유하기
      </button>

      <button
        className="flex flex-row items-center gap-2 px-5 rounded text-sm font-semibold text-white"
        style={{
          background: "#002045",
          boxShadow: "0px 1px 2px rgba(0,0,0,0.05)",
          borderRadius: "4px",
          fontFamily: "var(--font-alexandria)",
          height: "42px",
        }}
        onClick={onChatbot}
      >
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
          <circle cx="6" cy="6" r="5" stroke="white" strokeWidth="1.5" />
          <path d="M4 6h4M6 4v4" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
        챗봇에게 질문하기
      </button>
    </div>
  );
}
