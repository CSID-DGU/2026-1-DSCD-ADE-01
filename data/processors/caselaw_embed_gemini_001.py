"""
임베딩: gemini-embedding-001 (Vertex AI)
- case_law.csv 읽어서 issue 컬럼 임베딩
- embedding 컬럼은 JSON 문자열로 CSV 저장
- 인증: ADC (gcloud auth application-default login)
"""

import time, json
import pandas as pd
from google import genai
from google.genai import types
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
PROJECT_ID = os.getenv("GCP_PROJECT_ID")
LOCATION   = os.getenv("GCP_LOCATION", "us-central1")
MODEL       = 'gemini-embedding-001'

_BASE       = Path(__file__).resolve().parent.parent.parent
INPUT_CSV   = str(_BASE / "output" / "case_law.csv")
OUTPUT_FILE = str(_BASE / "output" / "case_law_with_embedding.csv")

# ── 데이터 로드 ───────────────────────────────────────────────────────────────
df = pd.read_csv(INPUT_CSV, encoding='utf-8-sig')
df['case_id']   = df['case_id'].astype(str)
df['embedding'] = None

targets = [(idx, r['issue']) for idx, r in df.iterrows()
           if pd.notna(r['issue']) and str(r['issue']).strip()]

print(f"로드: {len(df)}건 / 임베딩 대상: {len(targets)}건")

# ── Vertex AI 클라이언트 ──────────────────────────────────────────────────────
client = genai.Client(vertexai=True, project=PROJECT_ID, location=LOCATION)

# ── 임베딩 ────────────────────────────────────────────────────────────────────
errors = []
start  = time.time()

for i, (idx, text) in enumerate(targets):
    try:
        response = client.models.embed_content(
            model=MODEL,
            contents=text,
            config=types.EmbedContentConfig(
                task_type='RETRIEVAL_DOCUMENT',
                output_dimensionality=3072
            )
        )
        df.at[idx, 'embedding'] = json.dumps(response.embeddings[0].values)

        if (i + 1) % 50 == 0:
            elapsed = time.time() - start
            print(f"[{i+1}/{len(targets)}] {elapsed:.1f}s | 평균 {elapsed/(i+1):.2f}s/건")

        time.sleep(0.1)

    except Exception as e:
        errors.append({'case_id': df.at[idx, 'case_id'], 'error': str(e)})
        print(f"  오류 case_id={df.at[idx, 'case_id']}: {e}")

total = time.time() - start

# ── 저장 ─────────────────────────────────────────────────────────────────────
df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')

print(f"\n=== {MODEL} 완료 ===")
print(f"성공: {df['embedding'].notna().sum()}건 / 실패: {len(errors)}건")
print(f"총 소요시간: {total:.1f}s ({total/60:.1f}분)")
print(f"저장: {OUTPUT_FILE}")