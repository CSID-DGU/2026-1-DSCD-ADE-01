import { clausesFromLeaseInput } from "@/lib/contractAdapter";
import type { AnalyzeContractApiResponse, SpecialTermExpansionResult } from "@/types/api";
import type { ClauseAnalysis, ContractMock, GuideItem, LeaseContractInput } from "@/types/contract";

export const CONTRACT_ANALYSIS_STORAGE_KEY = "contractAnalysis.v1.result";

type BuildContractOptions = {
  displayFileName: string;
};

function toGeneralTitle(key: string): string {
  const n = Number(key.replace("art", ""));
  return Number.isFinite(n) ? `제${n}조` : key;
}

function cleanText(raw: string | null | undefined): string {
  if (!raw) return "";
  return raw
    .replace(/#/g, "")
    .replace(/🅓/g, "")
    .replace(/\|/g, " ")
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

function toSpecialSourcePath(item: SpecialTermExpansionResult, fallbackIndex: number): string {
  const n = typeof item.index === "number" && item.index >= 1 ? item.index : fallbackIndex + 1;
  return `special_terms.art${n}`;
}

function makeExpansionGuides(item: SpecialTermExpansionResult, i: number): GuideItem[] {
  const guides: GuideItem[] = [];
  const prefix = `special-exp-${i + 1}`;
  if (item.expansion.expansion_query) {
    guides.push({
      id: `${prefix}-query`,
      text: `확장 질의: ${item.expansion.expansion_query}`,
      checked: false,
    });
  }
  if (item.expansion.keywords.length > 0) {
    guides.push({
      id: `${prefix}-keywords`,
      text: `핵심 키워드: ${item.expansion.keywords.join(", ")}`,
      checked: false,
    });
  }
  return guides;
}

export function toContractViewModel(
  apiResult: AnalyzeContractApiResponse,
  options: BuildContractOptions,
): ContractMock {
  const art1Details = (apiResult.contract.general_terms?.art1 as { details?: Record<string, unknown> } | undefined)
    ?.details;
  const deposit = typeof art1Details?.deposit === "number" ? String(art1Details.deposit) : undefined;
  const monthlyRentAmount =
    typeof (art1Details?.monthly_rent as { amount?: unknown } | undefined)?.amount === "number"
      ? String((art1Details?.monthly_rent as { amount?: number }).amount)
      : undefined;
  const priorFixdate = apiResult.contract.property_info?.prior_fixdate ?? undefined;
  const taxArrears = apiResult.contract.property_info?.tax_arrears ?? undefined;

  const input: LeaseContractInput = {
    lease_type: apiResult.contract.lease_type,
    property_info: {
      address: apiResult.contract.property_info?.address ?? undefined,
      building_type:
        apiResult.contract.property_info?.building?.use ??
        apiResult.contract.property_info?.building?.structure ??
        undefined,
      leased_part: apiResult.contract.property_info?.leased_part?.detail_address ?? undefined,
      contract_type: apiResult.contract.property_info?.contract_kind?.type ?? undefined,
      deposit,
      monthly_rent: monthlyRentAmount,
      arrear_or_priority_registered: [taxArrears, priorFixdate].filter(Boolean).join(" / ") || undefined,
    },
    general_terms: Object.fromEntries(
      Object.entries(apiResult.contract.general_terms ?? {}).map(([key, value]) => [
        key,
        {
          title: toGeneralTitle(key),
          text: cleanText(value?.text),
        },
      ]),
    ),
    special_terms: Object.fromEntries(
      (apiResult.contract.special_terms ?? []).map((text, idx) => [
        `art${idx + 1}`,
        {
          title: `특약 ${idx + 1}`,
          text: cleanText(text),
        },
      ]),
    ),
  };

  const analysesBySourcePath: Record<string, ClauseAnalysis> = {};
  apiResult.special_term_expansions.forEach((item, i) => {
    analysesBySourcePath[toSpecialSourcePath(item, i)] = {
      relatedLaws: [],
      precedents: [],
      supplementGuide: makeExpansionGuides(item, i),
    };
  });

  return {
    id: `ctr_${Date.now()}`,
    title: "업로드 계약서 분석 결과",
    displayFileName: options.displayFileName,
    ...input,
    clauses: clausesFromLeaseInput(input, analysesBySourcePath),
  };
}

export function saveContractResult(contract: ContractMock): void {
  sessionStorage.setItem(CONTRACT_ANALYSIS_STORAGE_KEY, JSON.stringify(contract));
}

export function loadStoredContractResult(): ContractMock | null {
  const raw = sessionStorage.getItem(CONTRACT_ANALYSIS_STORAGE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as ContractMock;
  } catch {
    return null;
  }
}
