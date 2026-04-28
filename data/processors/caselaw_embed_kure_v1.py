"""
임베딩: KURE-v1 (로컬)
- case_law.csv 읽어서 issue 컬럼 임베딩
- embedding 컬럼은 JSON 문자열로 CSV 저장
- 설치: pip install sentence-transformers
"""

import time, json
import pandas as pd
from sentence_transformers import SentenceTransformer
from pathlib import Path

MODEL_NAME  = 'nlpai-lab/KURE-v1'
_BASE       = Path(__file__).resolve().parent.parent.parent
INPUT_CSV   = str(_BASE / "output" / "case_law.csv")
OUTPUT_FILE = str(_BASE / "output" / "case_law_with_embedding_kure.csv")
BATCH_SIZE  = 16

# ── 데이터 로드 ───────────────────────────────────────────────────────────────
df = pd.read_csv(INPUT_CSV, encoding='utf-8-sig')
df['case_id']   = df['case_id'].astype(str)
df['embedding'] = None

indices = [idx for idx, r in df.iterrows()
           if pd.notna(r['issue']) and str(r['issue']).strip()]
texts   = [str(df.at[idx, 'issue']) for idx in indices]

print(f"로드: {len(df)}건 / 임베딩 대상: {len(texts)}건")

# ── 모델 로드 ─────────────────────────────────────────────────────────────────
print(f"\n모델 로딩: {MODEL_NAME}")
load_start = time.time()
model = SentenceTransformer(MODEL_NAME)
print(f"로딩 완료: {time.time()-load_start:.1f}s")

# ── 임베딩 (배치) ─────────────────────────────────────────────────────────────
print(f"\n임베딩 시작 (batch_size={BATCH_SIZE})")
start = time.time()

embeddings = model.encode(
    texts,
    batch_size=BATCH_SIZE,
    show_progress_bar=True,
    normalize_embeddings=True
)

total = time.time() - start

# ── 결과를 원본 df에 삽입 ─────────────────────────────────────────────────────
for i, idx in enumerate(indices):
    df.at[idx, 'embedding'] = json.dumps(embeddings[i].tolist())

# ── 저장 ─────────────────────────────────────────────────────────────────────
df.to_csv(OUTPUT_FILE, index=False, encoding='utf-8-sig')

print(f"\n=== KURE-v1 완료 ===")
print(f"성공: {df['embedding'].notna().sum()}건 / 실패: {df['embedding'].isna().sum()}건")
print(f"총 소요시간: {total:.1f}s ({total/60:.1f}분)")
print(f"평균: {total/len(texts):.3f}s/건")
print(f"차원수: {embeddings.shape[1]}")
print(f"저장: {OUTPUT_FILE}")