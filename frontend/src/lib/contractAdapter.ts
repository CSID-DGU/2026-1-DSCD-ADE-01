import type {
  Clause,
  ClauseAnalysis,
  GeneralTerms,
  LeaseContractInput,
  SpecialTerms,
  TermArticle,
} from "@/types/contract";

export type ClauseViewItem = {
  id: string;
  group: "general_terms" | "special_terms";
  label: string;
  title: string;
  text: string;
  sourcePath: string;
};

const GENERAL_KEYS = [
  "art1",
  "art2",
  "art3",
  "art4",
  "art5",
  "art6",
  "art7",
  "art8",
  "art9",
  "art10",
  "art11",
  "art12",
  "art13",
] as const satisfies readonly (keyof GeneralTerms)[];

const SPECIAL_KEYS = ["art1", "art2", "art3", "art4", "art5"] as const satisfies readonly (keyof SpecialTerms)[];

function generalLabelFromKey(key: string): string {
  const n = Number(key.replace("art", ""));
  return Number.isFinite(n) ? `제${n}조` : key;
}

function specialLabelFromKey(key: string): string {
  const n = Number(key.replace("art", ""));
  return Number.isFinite(n) ? `특약 ${n}` : key;
}

function termToView(
  prefix: "general_terms" | "special_terms",
  key: string,
  article: TermArticle,
): ClauseViewItem {
  const sourcePath = `${prefix}.${key}`;
  const label = prefix === "general_terms" ? generalLabelFromKey(key) : specialLabelFromKey(key);
  const fallbackTitle =
    prefix === "special_terms" ? "특약사항" : generalLabelFromKey(key);
  const title = article.title?.trim() || fallbackTitle;

  return {
    id: sourcePath,
    group: prefix,
    label,
    title,
    text: article.text,
    sourcePath,
  };
}

/**
 * 입력 JSON을 목록 표시용 항목으로 변환합니다. 텍스트가 비어 있는 조항은 건너뜁니다.
 */
export function inputToClauseViewItems(input: LeaseContractInput): ClauseViewItem[] {
  const items: ClauseViewItem[] = [];
  GENERAL_KEYS.forEach((key) => {
    const art = input.general_terms?.[key];
    const text = art?.text?.trim();
    if (art && text) {
      items.push(termToView("general_terms", key, { ...art, text }));
    }
  });
  SPECIAL_KEYS.forEach((key) => {
    const art = input.special_terms?.[key];
    const text = art?.text?.trim();
    if (art && text) {
      items.push(termToView("special_terms", key, art));
    }
  });
  return items;
}

/**
 * 분석 결과는 sourcePath 키(예: general_terms.art3)로 매핑합니다.
 */
export function attachAnalysesToClauses(
  items: ClauseViewItem[],
  analysesBySourcePath: Record<string, ClauseAnalysis | undefined>,
): Clause[] {
  return items.map((v) => {
    const analysis = analysesBySourcePath[v.sourcePath] ?? emptyAnalysis();
    return {
      id: v.id,
      group: v.group,
      label: v.label,
      title: v.title,
      body: v.text,
      sourcePath: v.sourcePath,
      analysis,
    };
  });
}

export function clausesFromLeaseInput(
  input: LeaseContractInput,
  analysesBySourcePath: Record<string, ClauseAnalysis | undefined>,
): Clause[] {
  return attachAnalysesToClauses(inputToClauseViewItems(input), analysesBySourcePath);
}

function emptyAnalysis(): ClauseAnalysis {
  return {
    relatedLaws: [],
    precedents: [],
    supplementGuide: [] as ClauseAnalysis["supplementGuide"],
    clauseText: "",
    clauseRevision: undefined,
    contractChecklist: [],
    relatedClauses: [],
  };
}
