import { clausesFromLeaseInput } from "@/lib/contractAdapter";
import type { ClauseAnalysis, ContractMock, GuideItem, RecentDocument } from "@/types/contract";

function Gi(prefix: string, texts: string[]): GuideItem[] {
  return texts.map((text, i) => ({
    id: `${prefix}-g${i}`,
    text,
    checked: false,
  }));
}

const analysesBySourcePath: Record<string, ClauseAnalysis> = {
  "general_terms.art1": {
    relatedLaws: [
      {
        id: "l1",
        title: "주택임대차보호법",
        article: "제3조의2",
        summary:
          "임차인은 계약 체결 후 확정일자를 받아 우선변제권을 확보해야 한다.",
        fullText:
          "[주택임대차보호법 제3조의2 데모 원문]\n\n" +
          "임차인은 임대차계약서상의 날짜와 주민등록 등본 등에 의하여 대항력을 갖추고, 확정일자를 받은 임차권등기명령 등에 관한 규정에 따라 우선변제권을 행사할 수 있다. (요약·임시)",
        applicationReason:
          "목적 조항은 계약의 범위를 정의하므로, 주택임대차보호법상 ‘주택’ 해당 여부·대항요건 충족 여부를 해석할 때 출발점이 됩니다.",
      },
    ],
    precedents: [
      {
        id: "p1",
        title: "목적 조항의 해석 범위",
        caseNumber: "2023다XXXX",
        court: "대법원",
        tags: ["#임대차보호법", "#계약해석", "#목적조항"],
        summary:
          "목적 조항만으로 구체적 권리관계가 확정되지 않으므로 특약과 결합하여 해석해야 한다.",
        conflictSummary: "—",
        outcomeSummary: "—",
        originalText:
          "이 사건의 쟁점은 목적 조항이 구체적 의무까지 확정하는지 여부이며, 법원은 특약·부속합의와의 결합 해석을 전제로 판단하였다. (데모용 요약 원문)",
        supplementGuide: Gi("p1", [
          "본 판결은 특약 미비 시 목적물 특정 불명확으로 분쟁이 커질 수 있음을 시사합니다.",
        ]),
      },
    ],
    supplementGuide: Gi("art1", [
      "목적물 특정을 위해 주소·면적·등기부등본 반영 여부를 특약에 명시할 것.",
    ]),
  },
  "general_terms.art2": {
    relatedLaws: [
      {
        id: "l2",
        title: "민법",
        article: "제618조",
        summary:
          "임차인은 계약 종료 시 목적물 반환과 함께 보증금 반환을 청구할 수 있다.",
        fullText:
          "[민법 제618조 데모 원문]\n\n" +
          "임차인이 임대인에게 보증금을 지급한 경우에는 임대차가 종료한 때에 임대인은 그 보증금을 임차인에게 반환하여야 한다. (요약·임시)",
        applicationReason:
          "본 조항은 보증금 반환 청구의 법적 근거가 되며, 반환 시기·지연손해금 특약과 함께 해석됩니다.",
        warning: {
          level: "위험",
          title: "반환 시기 불명확",
          reason:
            "계약서상 보증금 반환 시기가 ‘즉시’로만 표기되어 분쟁 소지가 있습니다.",
          detail:
            "‘즉시’는 영업일 기준인지, 퇴거 검수 완료 후인지, 이자 발생 시점 등이 불명확하여 소송에서 쟁점이 되기 쉽습니다. 반환 절차(검수 → 정산 → 이체)를 단계별로 특약에 적시하는 것이 안전합니다.",
        },
      },
    ],
    precedents: [],
    supplementGuide: Gi("art2", [
      "반환 기한을 영업일 기준 ○일 이내로 명확히 적시하고, 연체 시 지연손해금을 규정할 것.",
    ]),
  },
  "general_terms.art3": {
    relatedLaws: [
      {
        id: "l3",
        title: "민법",
        article: "제623조",
        summary:
          "차임연체액이 임차료의 2기분에 달하면 계약해지 사유가 될 수 있다.",
        fullText:
          "[민법 제623조 데모 원문]\n\n" +
          "임차인이 차임의 지급을 지체한 때에는 임대인은 상당한 기간을 정하여 그 기간 내에 지급하지 아니하면 계약을 해지할 수 있다는 취지의 규정이 적용될 수 있다. (요약·임시)",
        applicationReason:
          "임차료 연체와 해지 사유의 관계를 설명할 때 핵심 조문으로, 특약상 해지 조건과의 관계를 함께 검토합니다.",
      },
    ],
    precedents: [
      {
        id: "p2",
        title: "임차료 연체와 계약 해지",
        caseNumber: "2022가합XXXX",
        court: "서울중앙지방법원",
        tags: ["#해지통고", "#임대차보호법", "#연체해지"],
        summary:
          "임차료 연체 해지 특약은 형평에 반하지 않는 한 유효하다고 보았음.",
        conflictSummary:
          "임대인 요구 해지 통고와 통상 해지 특약 간 해석 충돌 여부가 쟁점임.",
        outcomeSummary:
          "통고 기간 및 유예 특약 명시 여부가 실무 분쟁 완화에 유리함.",
        originalText:
          "원고는 임차료 연체를 이유로 계약해지를 주장하였고, 법원은 통고 절차와 유예기간 특약의 존재를 중심으로 판단하였다. (데모용)",
        supplementGuide: Gi("p2", [
          "해지 통고가 있었다면 「통고 내용·수령일」을 부속 증거로 확보하고, 특약 유예 조항 존재 여부를 교차 확인할 것.",
        ]),
      },
    ],
    supplementGuide: Gi("art3", [
      "연체 시 해지까지의 유예기간과 통지 방법을 특약으로 추가할 것.",
    ]),
  },
  "general_terms.art4": {
    relatedLaws: [
      {
        id: "l4",
        title: "민법",
        article: "제623조의2",
        summary:
          "임차인은 필요비 상환청구 및 유익비 중 현존 증가액 상환청구가 가능할 수 있다.",
        fullText:
          "[민법 제623조의2 데모 원문]\n\n" +
          "임차인은 임차물의 유지에 필요한 비용을 지출한 때에는 임대인에게 그 상환을 청구할 수 있다. (요약·임시)",
        applicationReason:
          "설비 교체·수선 비용이 필요비·유익비·통상적 수선 중 어디에 해당하는지 판단할 때 참고됩니다.",
        warning: {
          level: "주의",
          title: "통상적 수선 범위 모호",
          reason:
            "‘통상의 수선’ 정의가 없어 장비 교체·도장 등 비용 분담 분쟁이 발생할 수 있습니다.",
          detail:
            "에어컨·보일러 등 내구연한이 도래한 설비는 ‘통상’ 범위인지 별도 합의가 필요한지가 분쟁의 중심입니다. 설비별 내용연수·교체 이력을 특약 부속으로 두면 해석이 수월합니다.",
        },
      },
    ],
    precedents: [
      {
        id: "p4",
        title: "설비 교체 비용 분담·통상적 수선 범위",
        caseNumber: "2020가단XXXX",
        court: "서울남부지방법원",
        tags: ["#수선", "#설비교체", "#유익비"],
        summary:
          "임차 목적물의 에어컨 등 설비 교체가 통상적인 유지관리 범위인지, 유익비·필요비 여부와 함께 내구연한을 기준으로 판단하였음.",
        conflictSummary:
          "임대인은 침실 에어컨 교체 비용 전액을 임차인 부담으로 주장했으나, 내구연한 초과 여부가 핵심 쟁점입니다.",
        outcomeSummary:
          "판례상 원상회복 의무와 분리하여 소모품 교체 비용은 특약 없으면 협의 해석에 따름.",
        originalText:
          "이 사건에서 법원은 설비의 내용연한·사용 상태·거래관행을 종합하여 통상적 수선 범위를 좁게 해석하였다. (데모용 임시 판례 전문)",
        supplementGuide: Gi("p4", [
          "설비 교체 전에 상태·예상 내용연수·부담 주체를 이메일·카톡 등으로 합의한 흔적을 남길 것.",
        ]),
      },
    ],
    supplementGuide: Gi("art4", [
      "내구연한 표준표를 부속합의서로 첨부하고 필수 설비 교체 비용 귀속을 명시할 것.",
    ]),
  },
  "special_terms.art1": {
    relatedLaws: [
      {
        id: "l5",
        title: "민법",
        article: "제627조",
        summary:
          "임차인은 사용 종료 후 원상회복 의무가 있으며 특별 손상 시 배상 책임이 발생한다.",
        fullText:
          "[민법 제627조 데모 원문]\n\n" +
          "임차인은 임차물을 원상에 회복하여 임대인에게 반환하여야 한다. (요약·임시)",
        applicationReason:
          "원상복구 특약이 민법상 원상회복 의무와 어떻게 맞물리는지, ‘통상 마모’ 예외가 유효한지 해석할 때 기준이 됩니다.",
        warning: {
          level: "위법가능",
          title: "원상복구 범위 불명확",
          reason:
            "‘통상 마모 제외’만으로는 도장·바닥 상태 등 세부 기준이 불분명합니다.",
          detail:
            "퇴거 시 ‘원상’의 기준(입주 당시 사진 대비)이 없으면 임대인·임차인 주장이 크게 엇갈립니다. 체크리스트·사진·하자 구분표를 특약에 포함하세요.",
        },
      },
    ],
    precedents: [
      {
        id: "p3",
        title: "원상복구 범위와 거래관행",
        caseNumber: "2021나XXXX",
        court: "서울고등법원",
        tags: ["#묵시적갱신", "#해지통고", "#임대차보호법"],
        summary:
          "원상복구 범위는 객관적 거래관행과 목적물 최초 상태를 고려하여 해석함.",
        conflictSummary:
          "임대인 요구 범위와 임차인 인정 범위 간 차이가 커 추가 특약 없으면 종료 시 분쟁 가능성이 높음.",
        outcomeSummary:
          "반환 검수 체크리스트와 사진 증빙 절차를 마련하면 분쟁 완화에 유리함.",
        originalText:
          "원상복구에 관하여 법원은 거래관행상 통상적으로 인정되는 범위와 당사자 합의의 존재를 중시하였다. (데모용)",
        supplementGuide: Gi("p3", [
          "본 판례 관점에서는 반환 시점 증거(사진·검수표) 확보 여부가 손실의 범위를 좁히는 데 특히 유리했습니다.",
        ]),
      },
    ],
    supplementGuide: Gi("sp1", [
      "입주 전·퇴거 전 상태 사진 교환 일정과 하자 항목 분류표를 특약으로 첨부할 것.",
      "중개사 또는 제3자 검수 합의 조항을 추가할 것.",
    ]),
  },
};

const leaseInputBody = {
  id: "ctr_mock_001",
  title: "서울특별시 강서구 단독주택 임대차 계약서",
  displayFileName: "공덕동_주택 임대차계약서.pdf",
  lease_type: "주택임대차",
  property_info: {
    lease_category: "주택 임대차",
    address: "서울특별시 강서구 화곡동 123",
    building_type: "단독주택",
    leased_part: "전층 (지상 1층·2층)",
    contract_type: "신규",
    deposit: "금 삼천만 원",
    monthly_rent: "금 구십만 원 (매월 선불)",
    arrear_or_priority_registered: "미기재",
  },
  general_terms: {
    art1: {
      title: "목적",
      text: "본 계약은 임대인과 임차인 간 임대목적물의 사용·수익에 관한 사항을 정함을 목적으로 한다.",
    },
    art2: {
      title: "보증금",
      text: "임차인은 임대보증금 금 삼천만 원을 계약 체결 시 임대인에게 지급한다.",
    },
    art3: {
      title: "임차료",
      text: "임차료는 매월 선불 금 구십만 원으로 하며 매월 말일까지 지급한다.",
    },
    art4: {
      title: "수선",
      text: "임차인은 통상의 수선 부담을 지며, 구조 변경은 임대인 서면 동의를 받아야 한다.",
    },
  },
  special_terms: {
    art1: {
      title: "특약사항",
      text:
        "임차인은 계약 종료 시 원상복구 후 반환하며, 원상복구 비용은 별도 협의한다. 단, 통상 마모는 제외한다.",
    },
  },
};

export const mockContract: ContractMock = {
  ...leaseInputBody,
  clauses: clausesFromLeaseInput(
    {
      lease_type: leaseInputBody.lease_type,
      property_info: leaseInputBody.property_info,
      general_terms: leaseInputBody.general_terms,
      special_terms: leaseInputBody.special_terms,
    },
    analysesBySourcePath,
  ),
};

export const recentDocuments: RecentDocument[] = [
  {
    id: "d1",
    title: "강남구 다가구 주택 임대차 계약서",
    updatedAt: "2025.04.28",
  },
  {
    id: "d2",
    title: "사업자 간 사무실 임대차 초안",
    updatedAt: "2025.04.20",
  },
  {
    id: "d3",
    title: "○○아파트 전세계약서",
    updatedAt: "2025.04.12",
  },
];
