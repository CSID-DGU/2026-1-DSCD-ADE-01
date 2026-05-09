import type { AnalyzeContractApiResponse } from "@/types/api";

export type V1PipelineResult = {
  data: AnalyzeContractApiResponse;
  expansionSkipped: boolean;
  expansionSkipReason?: string;
};

/**
 * v1 파이프라인: 먼저 /v1/contracts/analyze 를 호출하고,
 * Query Expansion 등으로 실패하면 /v1/contracts/parse 로 폴백해 파싱 결과만 사용합니다.
 */
export async function runV1ContractPipeline(file: File): Promise<V1PipelineResult> {
  const analyzeForm = new FormData();
  analyzeForm.append("file", file);

  const analyzeRes = await fetch("/api/contracts/analyze", {
    method: "POST",
    body: analyzeForm,
  });

  if (analyzeRes.ok) {
    const data = (await analyzeRes.json()) as AnalyzeContractApiResponse;
    return { data, expansionSkipped: false };
  }

  let expansionSkipReason: string | undefined;
  try {
    const err = (await analyzeRes.json()) as { detail?: unknown };
    if (typeof err.detail === "string") expansionSkipReason = err.detail;
  } catch {
    expansionSkipReason = undefined;
  }

  const parseForm = new FormData();
  parseForm.append("file", file, file.name);

  const parseRes = await fetch("/api/contracts/parse", {
    method: "POST",
    body: parseForm,
  });

  if (!parseRes.ok) {
    throw new Error(
      "계약서 분석 요청에 실패했고, 파싱 폴백도 실패했습니다. 잠시 후 다시 시도해 주세요.",
    );
  }

  const contract = (await parseRes.json()) as AnalyzeContractApiResponse["contract"];

  return {
    data: {
      contract,
      special_term_expansions: [],
    },
    expansionSkipped: true,
    expansionSkipReason,
  };
}
