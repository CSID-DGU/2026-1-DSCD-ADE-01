"use client";

import { useEffect, useState } from "react";
import { TopNavBar } from "@/components/TopNavBar";
import { DocumentPanel } from "@/components/analysis/DocumentPanel";
import { LawSection } from "@/components/analysis/LawSection";
import { PrecedentSection } from "@/components/analysis/PrecedentSection";
import { BottomActionBar } from "@/components/analysis/BottomActionBar";
import type { LawItem } from "@/components/analysis/LawSection";
import type { PrecedentItem } from "@/components/analysis/PrecedentSection";

/* ─── Mock data (실제 API 연동 전 표시용) ─────────────────────────── */

const MOCK_LAWS: LawItem[] = [
  {
    rank: 1,
    name: "민법 제635조 (기간의 약정없는 임대차의 해지통고)",
  },
  {
    rank: 2,
    name: "주택임대차보호법 제6조의2 (묵시적 갱신의 경우 계약의 해지)",
    warning: "해당 법령에 대한 위법 사항이 있습니다. 즉각 조치가 필요합니다.",
    detail:
      "계약서 제3조 2항의 해지 효력 발생 기간(1개월)이 강행규정인 주택임대차보호법 제6조의2 제2항(3개월)에 위배되어 임차인에게 불리하므로 무효임.",
  },
];

const MOCK_PRECEDENTS: PrecedentItem[] = [
  {
    title: "대법원 2021.X.X. 선고 2020다XXXXX 판결",
    tags: ["#묵시적갱신", "#해지통고", "#임대차보호법"],
    facts: [
      {
        label: "핵심충돌",
        text: "묵시적 갱신 시 해지권 행사 시점의 효력 발생 여부.",
      },
      {
        label: "결과",
        text: "원고 승소 - 해지 통고 후 3개월 경과 시 효력 발생. 강행 규정에 반하는 특약은 무효임을 확인",
      },
    ],
    guide: [
      { id: "g1", text: "확인사항: 계약서 3조 2항 검토 완료", checked: true },
      { id: "g2", text: "누락된 사항: 강행규정 위반 시 효력에 대한 조항 부재", checked: false },
      { id: "g3", text: "모호한 어휘: '언제든지' 라는 표현의 구체화 필요", checked: false },
      { id: "g4", text: "수치 확인: 해지 효력 발생 기간 (1개월 → 3개월) 수정 요망", checked: false },
    ],
  },
];

const MOCK_ARTICLES = [
  { title: "제 1 조", items: ["본 계약은 임대인과 임차인 간의 주택 임대차에 관한 권리와 의무를 규정함을 목적으로 한다."] },
  { title: "제 2조", items: ["임대차 기간은 2024년 1월 1일부터 2026년 12월 31일까지 (24개월)로 한다."] },
  {
    title: "제 3조",
    items: [
      "① 임대인 또는 임차인이 임대차기간이 끝나기 6개월 전부터 2개월 전까지의 기간에 서로에게 갱신거절의 통지를 하지 아니하거나 계약조건을 변경하지 아니하면 갱신하지 아니한다는 뜻의 통지를 하지 아니한 경우에는 그 기간이 끝난 때에 전 임대차와 동일한 조건으로 다시 임대차한 것으로 본다.",
      "② 제 1항의 경우 임대차의 존속기간은 2년으로 본다. 단, 임차인은 언제든지 임대인에게 계약해지를 통지할 수 있으며, 이 경우 통지가 임대인에게 도달한 날부터 1개월이 경과하면 그 효력이 발생한다.",
    ],
  },
  {
    title: "제 5 조 (특약사항)",
    items: [
      "① 부동산의 소유권등기시 은행업무 처리기간 확인 후 그 기간동안 임차인은 전출하여야 한다. 이때 근저당 원금 3.9억원 이외의 권리변동(추가 근저당 및 압류등)시 임대인이 손해배상하고, 임차인의 전출 불이행으로 인해 임대인의 손해 발생 시 임차인이 손해배상하기로 한다.",
      "② 임차인은 계약종료 3개월전 임대인에 갱신을 요구하면 임대인은 최대한 협조한다",
      "③ 임대인은 본 부동산에 계약일부터 계약종료일까지 추가 권리(근저당권, 압류, 가압류, 가처분 등)를 설정하지 않는다. 이를 1개월 이내 해결하지 못할 시 계약을 해지하고 보증금 반환과 별도로 계약금에 준하는 손해배상금을 임차인에게 지급한다.",
    ],
  },
];

/* ─── Page ─────────────────────────────────────────────────────────── */

export default function AnalysisPage() {
  const [fileName, setFileName] = useState<string>("공덕동_주택 임대차계약서.pdf");

  useEffect(() => {
    const stored = sessionStorage.getItem("ade.analysis.fileName");
    if (stored) setFileName(stored);
  }, []);

  return (
    <div className="flex flex-col h-screen overflow-hidden" style={{ background: "#F4F3F7" }}>
      <TopNavBar
        mode="analysis"
        fileName={fileName}
        analysisStatus="done"
        activeTab="analysis"
      />

      {/* Split view */}
      <div className="flex flex-row flex-1 min-h-0">
        {/* Left: Document */}
        <DocumentPanel articles={MOCK_ARTICLES} />

        {/* Right: Analysis results */}
        <section
          className="flex flex-col flex-1 overflow-y-auto"
          style={{ background: "#FAF9FD", padding: "32px 32px 128px", gap: "32px" }}
        >
          <LawSection laws={MOCK_LAWS} />
          <PrecedentSection precedents={MOCK_PRECEDENTS} />
        </section>
      </div>

      <BottomActionBar />
    </div>
  );
}
