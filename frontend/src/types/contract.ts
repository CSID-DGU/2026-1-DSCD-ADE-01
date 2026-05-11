export type LawWarningLevel = "주의" | "위험" | "위법가능";

export type LawWarning = {
  level: LawWarningLevel;
  title: string;
  reason: string;
  detail?: string;
};

export type LawItem = {
  id: string;
  title: string;
  article?: string;
  summary: string;
  violationStatus?: "안전" | "문제없음" | "주의" | "위법가능" | "위법소지높음";
  violationReason?: string;
  fullText?: string;
  applicationReason?: string;
  warning?: LawWarning;
};

export type GuideItem = {
  id: string;
  text: string;
  checked?: boolean;
};

export type PrecedentItem = {
  id: string;
  title?: string;
  caseNumber?: string;
  court?: string;
  tags?: string[];
  summary: string;
  implication?: string;
  conflictSummary?: string;
  outcomeSummary?: string;
  originalText?: string;
  supplementGuide?: GuideItem[];
};

export type ClauseRevision = {
  target: string;
  reason: string;
  direction: string;
};

export type ContractChecklistItem = {
  id: string;
  item: string;
  description: string;
  basis: string;
  checked?: boolean;
};

export type RelatedClauseItem = {
  clauseId: string;
  clauseText: string;
  relation: string;
};

export type ClauseAnalysis = {
  relatedLaws: LawItem[];
  precedents: PrecedentItem[];
  supplementGuide: GuideItem[];
  clauseText?: string;
  clauseRevision?: ClauseRevision;
  contractChecklist?: ContractChecklistItem[];
  relatedClauses?: RelatedClauseItem[];
};

export type ClauseGroup = "general_terms" | "special_terms";

export type Clause = {
  id: string;
  group: ClauseGroup;
  label: string;
  title: string;
  body: string;
  sourcePath: string;
  analysis: ClauseAnalysis;
};

/** 입력 계약서 JSON의 조항 블록 (art1 …) */
export type TermArticle = {
  title?: string;
  text: string;
};

export type PropertyInfo = {
  lease_category?: string;
  address?: string;
  building_type?: string;
  leased_part?: string;
  contract_type?: string;
  deposit?: string;
  monthly_rent?: string;
  arrear_or_priority_registered?: string;
};

export type GeneralTerms = {
  art1?: TermArticle;
  art2?: TermArticle;
  art3?: TermArticle;
  art4?: TermArticle;
  art5?: TermArticle;
  art6?: TermArticle;
  art7?: TermArticle;
  art8?: TermArticle;
  art9?: TermArticle;
  art10?: TermArticle;
  art11?: TermArticle;
  art12?: TermArticle;
  art13?: TermArticle;
};

export type SpecialTerms = {
  art1?: TermArticle;
  art2?: TermArticle;
  art3?: TermArticle;
  art4?: TermArticle;
  art5?: TermArticle;
};

/** 백엔드/OCR 입력 스키마 */
export type LeaseContractInput = {
  lease_type?: string;
  property_info?: PropertyInfo;
  general_terms?: GeneralTerms;
  special_terms?: SpecialTerms;
};

export type ContractMock = LeaseContractInput & {
  id: string;
  title: string;
  displayFileName: string;
  clauses: Clause[];
};

export type RecentDocument = {
  id: string;
  title: string;
  updatedAt: string;
};

export type ChatbotSource = "law" | "precedent" | "guide";

export type ChatbotOpenDetail = {
  initialMessage?: string;
  context?: {
    clauseId: string;
    clauseLabel: string;
    clauseSourcePath?: string;
    source: ChatbotSource;
  };
};
