"use client";

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

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

  // Simple pre-processor for messy table syntax
  const preprocessMarkdown = (text: string) => {
    if (!text) return "";
    
    // 1. If there are no newlines but many pipes, it's likely row-stuck.
    // Replace "| |" with "|\n|" to force newlines between rows.
    let processed = text.replace(/\|\s*\|/g, '|\n|');
    
    // 2. Handle the |-|-| separator
    if (processed.includes('|-|-|')) {
      const lines = processed.split('\n');
      const newLines: string[] = [];
      
      lines.forEach(line => {
        if (line.includes('|-|-|')) {
          // If the line has text before |-|-|, push the text first, then a dummy header
          const parts = line.split('|-|-|');
          const before = parts[0].trim();
          
          if (before) {
            newLines.push(before);
          }
          
          // Generate a reasonable separator (cap at 10 columns)
          // Count pipes in the NEXT line to guess columns
          const nextLine = lines[lines.indexOf(line) + 1] || "";
          const pipeCount = (nextLine.match(/\|/g) || []).length;
          const colCount = Math.min(Math.max(pipeCount, 3), 10);
          
          // Dummy header row
          newLines.push('|' + Array(colCount).fill(' ').join('|') + '|');
          // Standard separator row
          newLines.push('|' + Array(colCount).fill('---').join('|') + '|');
        } else {
          newLines.push(line);
        }
      });
      processed = newLines.join('\n');
    }
    
    return processed;
  };

  const MarkdownComponents = {
    table: ({...props}) => (
      <div className="my-4 overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full border-collapse text-xs" {...props} />
      </div>
    ),
    thead: ({...props}) => <thead className="bg-gray-50" {...props} />,
    th: ({...props}) => <th className="border-b border-gray-200 px-3 py-2 text-left font-bold text-gray-700" {...props} />,
    td: ({...props}) => <td className="border-b border-gray-100 px-3 py-2 text-gray-600 leading-relaxed" {...props} />,
    p: ({...props}) => <p className="mb-2 last:mb-0" {...props} />,
  };

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
        {/* 1. 분석 대상 특약 사항 */}
        {specialTerms.length > 0 && (
          <div className="flex flex-col gap-4">
            <h3 className="px-2 text-sm font-black text-blue-700 uppercase tracking-widest border-l-4 border-blue-600">
              특약 사항
            </h3>
            <div className="flex flex-col gap-2">
              {specialTerms.slice(6).map((text, i) => {
                const absoluteIndex = i + 6;
                return (
                  <button
                    key={`target-${i}`}
                    onClick={() => onTermClick?.(absoluteIndex)}
                    className="group flex flex-col gap-1 rounded-lg border border-gray-200 bg-white p-4 text-left transition hover:border-blue-300 hover:bg-blue-50 hover:shadow-sm"
                  >
                    <span className="text-[10px] font-bold text-gray-400 uppercase group-hover:text-blue-500">
                      특약 {i + 1}
                    </span>
                    <div className="text-sm text-gray-800 leading-relaxed font-medium">
                      <ReactMarkdown 
                        remarkPlugins={[remarkGfm]}
                        components={MarkdownComponents}
                      >
                        {preprocessMarkdown(text)}
                      </ReactMarkdown>
                    </div>
                  </button>
                );
              })}
              {specialTerms.length <= 6 && (
                <p className="text-xs text-gray-400 italic px-3">추가 특약 없음</p>
              )}
            </div>
          </div>
        )}

        {/* 2. 공통 특약 */}
        {specialTerms.length >= 6 && (
          <div className="flex flex-col gap-4">
            <h3 className="px-2 text-sm font-black text-blue-700 uppercase tracking-widest border-l-4 border-blue-600">
              공통 특약
            </h3>
            <div className="flex flex-col gap-2">
              {specialTerms.slice(0, 6).map((text, i) => (
                <div
                  key={`common-${i}`}
                  className="flex flex-col gap-1 rounded-lg border border-gray-200 bg-white p-4 text-left"
                >
                  <span className="text-[10px] font-bold text-gray-400 uppercase">
                    공통특약 {i + 1}
                  </span>
                  <div className="text-sm text-gray-800 leading-relaxed font-medium">
                    <ReactMarkdown 
                      remarkPlugins={[remarkGfm]}
                      components={MarkdownComponents}
                    >
                      {preprocessMarkdown(text)}
                    </ReactMarkdown>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* 구분선 */}
        <div className="h-px bg-gray-100 mx-2" />

        {/* 3. 일반 조항 섹션 */}
        {generalTerms.length > 0 && (
          <div className="flex flex-col gap-4">
            <h3 className="px-2 text-sm font-black text-blue-700 uppercase tracking-widest border-l-4 border-blue-600">
              일반 조항
            </h3>
            <div className="flex flex-col gap-4">
              {generalTerms.map((term, i) => (
                <div key={i} className="flex flex-col gap-1 rounded-lg border border-gray-200 bg-white p-4 text-left">
                  <span className="text-[10px] font-bold text-gray-400 uppercase">{term.title}</span>
                  <div className="text-sm text-gray-800 leading-relaxed font-medium">
                    <ReactMarkdown 
                      remarkPlugins={[remarkGfm]}
                      components={MarkdownComponents}
                    >
                      {preprocessMarkdown(term.text)}
                    </ReactMarkdown>
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
