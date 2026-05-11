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
        id: "law-sp1-1",
        title: "주택임대차보호법",
        article: "제6조",
        summary:
          "임대차기간이 끝나기 2개월 전까지 임대인 또는 임차인이 갱신거절 통지를 하지 않으면 동일한 조건으로 다시 임대차한 것으로 보는 묵시적 갱신 규정입니다.",
        violationStatus: "주의",
        violationReason:
          "특약이 만기 2개월 전 통보 의무를 정한 점은 묵시적 갱신 제도와 관련됩니다. 다만 통보 수신자에 부동산 중개사가 포함되어 있어, 중개사에게 한 통보가 임대인에게 한 통보와 같은 효력을 갖는지 불분명합니다.",
      },
      {
        id: "law-sp1-2",
        title: "민법",
        article: "제111조",
        summary:
          "상대방 있는 의사표시는 그 통지가 상대방에게 도달한 때 효력이 발생한다는 의사표시 도달주의에 관한 규정입니다.",
        violationStatus: "안전",
      },
    ],
    precedents: [
      {
        id: "prec-sp1-1",
        title: "묵시적 갱신과 갱신거절 통지의 도달 여부",
        caseNumber: "2021나8265",
        court: "서울고등법원",
        tags: [],
        summary:
          "임대차 종료 또는 갱신거절 의사표시는 계약 상대방에게 명확히 도달해야 하며, 도달 여부가 불분명하면 묵시적 갱신 여부가 분쟁의 핵심이 될 수 있습니다.",
        conflictSummary:
          "쟁점은 임차인의 갱신거절 통지가 임대인에게 적법하게 도달했는지 여부였습니다. 임차인은 중개사 전달 사실로 통지의 효력을 주장했고, 임대인은 본인에게 직접 도달하지 않았다는 점을 들어 묵시적 갱신 성립을 주장했습니다.",
        outcomeSummary:
          "법원은 상대방 있는 의사표시는 계약 상대방에게 도달해야 효력이 발생한다고 보아, 도달 입증이 부족한 통지는 갱신거절의 효력을 인정하기 어렵다고 판단했습니다. 따라서 임차인의 조기 종료 주장 및 관련 비용 면제 주장은 제한되었습니다.",
      },
    ],
    supplementGuide: [],
    clauseText:
      "임차인은 연장의사가 없을 경우, 퇴실 또는 재계약 여부를 만기 2개월 전까지 임대인 및 부동산 중개사에게 통보하기로 한다.",
    clauseRevision: {
      target: "부동산 중개사에게 통보",
      reason:
        "임대차계약의 당사자가 아닌 중개사가 통보의 수신자로 포함되어 있어, 중개사에 대한 통보가 임대인에게 한 것과 동일한 법적 효력을 갖는지 불분명하여 해석상 분쟁이 발생할 수 있습니다.",
      direction:
        "통보 대상을 계약 당사자인 '임대인'으로 한정하거나, '중개사에 대한 통보는 임대인의 편의를 위한 보조적 전달 절차이며 법적 효력은 임대인에게 도달한 때 발생한다'는 점을 명시합니다.",
    },
    contractChecklist: [
      {
        id: "check-sp1-1",
        item: "갱신거절 또는 퇴실 통보 기한 확인",
        description:
          "계약 만료 2개월 전까지 통보해야 하는지, 법정 통보기한과 계약서 특약이 충돌하지 않는지 확인합니다.",
        basis: "주택임대차보호법 제6조",
        checked: false,
      },
      {
        id: "check-sp1-2",
        item: "통보 수신자 명확화",
        description:
          "퇴실 또는 재계약 의사는 임대인에게 직접 통보되도록 하고, 중개사는 보조 수신자인지 명확히 구분합니다.",
        basis: "민법상 의사표시 도달 원칙",
        checked: false,
      },
      {
        id: "check-sp1-3",
        item: "통보 증빙 방식 확보",
        description:
          "문자, 카카오톡, 이메일, 내용증명 등 통보 일자와 수신 여부를 입증할 수 있는 방식을 정합니다.",
        basis: "분쟁 예방을 위한 계약 이행 증빙",
        checked: false,
      },
    ],
    relatedClauses: [
      {
        clauseId: "특약2",
        clauseText:
          "계약기간 만료 전 퇴실 시 또는 묵시적 갱신으로 인한 퇴실 시, 중개보수료, 월세, 관리비는 임차인이 부담한다.",
        relation:
          "본 특약에 따른 통보를 하지 않아 계약이 묵시적으로 갱신된 경우, 임차인이 갱신된 기간 중 계약 해지를 통지하고 퇴거하면 특약2에 따라 중개보수 등의 비용 부담 문제가 발생할 수 있습니다. 따라서 통보 의무와 비용 부담 조항은 함께 검토해야 합니다.",
      },
    ],
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
      title: "보증금과 차임 및 관리비",
      text:
        "위 부동산의 임대차에 관하여 임대인과 임차인은 합의에 의하여 보증금과 차임 및 관리비를 아래와 같이 지불하기로 한다.",
    },
    art2: {
      title: "임대차기간",
      text:
        "임대인은 임차주택을 임대차 목적으로 사용·수익할 수 있는 상태로 2023년 04월 26일까지 임차인에게 인도하고, 임대차기간은 인도일로부터 2025년 04월 26일까지로 한다.",
    },
    art3: {
      title: "입주 전 수리",
      text:
        "임대인과 임차인은 임차주택의 수리가 필요한 시설물 및 비용부담에 관하여 다음과 같이 합의한다.",
    },
    art4: {
      title: "임차주택의 사용·관리·수선",
      text:
        "① 임차인은 임대인의 동의 없이 임차주택의 구조변경 및 전대나 임차권 양도를 할 수 없으며, 임대차 목적인 주거 이외의 용도로 사용할 수 없다.\n" +
        "② 임대인은 계약 존속 중 임차주택을 사용·수익에 필요한 상태로 유지하여야 하고, 임차인은 임대인이 임차주택의 보존에 필요한 행위를 하는 때 이를 거절하지 못한다.\n" +
        "③ 임대인과 임차인은 계약 존속 중에 발생하는 임차주택의 수리 및 비용부담에 관하여 다음과 같이 합의한다.",
    },
    art5: {
      title: "계약의 해제",
      text:
        "임차인이 임대인에게 중도금(중도금이 없을 때는 잔금)을 지급하기 전까지, 임대인은 계약금의 배액을 상환하고, 임차인은 계약금을 포기하고 이 계약을 해제할 수 있다.",
    },
  },
  special_terms: {
    art1: {
      title: "특약사항",
      text:
        "임차인은 연장의사가 없을 경우, 퇴실 또는 재계약 여부를 만기 2개월 전까지 임대인 및 부동산 중개사에게 통보하기로 한다.",
    },
    art2: {
      title: "특약사항",
      text:
        "계약기간 만료 전 퇴실 시 또는 묵시적 갱신으로 인한 퇴실 시, 중개보수료, 월세, 관리비는 임차인이 부담한다.",
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
