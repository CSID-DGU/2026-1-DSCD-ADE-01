import { NextResponse } from "next/server";

const API_BASE_URL =
  process.env.CONTRACT_API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "https://ade-contract-api-909552898356.us-central1.run.app";

export async function POST(request: Request) {
  try {
    const incoming = await request.formData();
    const file = incoming.get("file");

    if (!(file instanceof File)) {
      return NextResponse.json({ detail: "file 필드가 필요합니다." }, { status: 400 });
    }

    const formData = new FormData();
    formData.append("file", file, file.name);

    const upstream = await fetch(`${API_BASE_URL}/v1/contracts/parse`, {
      method: "POST",
      body: formData,
      cache: "no-store",
    });

    const contentType = upstream.headers.get("content-type") ?? "";
    if (contentType.includes("application/json")) {
      const json = await upstream.json();
      return NextResponse.json(json, { status: upstream.status });
    }

    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: { "content-type": contentType || "text/plain; charset=utf-8" },
    });
  } catch {
    return NextResponse.json(
      { detail: "파싱 서버와 통신 중 오류가 발생했습니다." },
      { status: 502 },
    );
  }
}
