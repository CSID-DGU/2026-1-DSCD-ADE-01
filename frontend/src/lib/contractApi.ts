import type { AnalyzeContractApiResponse } from "@/types/api";

export async function analyzeContract(file: File): Promise<AnalyzeContractApiResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch("/api/contracts/analyze", {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    throw new Error("계약서 분석 요청에 실패했습니다.");
  }

  return res.json() as Promise<AnalyzeContractApiResponse>;
}
