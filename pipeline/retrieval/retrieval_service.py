"""FastAPI lifespan에서 1회 로드되는 검색 서비스 싱글턴.

Dense 유사도 검색은 in-memory numpy 대신 PostgreSQL pgvector (<=> 코사인 거리)에 위임한다.
→ load() 시 임베딩 벡터를 메모리에 올리지 않아 RAM 사용량이 대폭 줄어든다.

의존 관계:
  BM25  : pipeline.retrieval.bm25_retrieval (tokenize, build_query_tokens, load_*_from_db)
  Embed : pipeline.retrieval.dense_retrieval (embed_query — Vertex AI 호출)
  DB    : shared.db.connection (pgvector 쿼리)

무거운 import (Kiwi NLP 모델, Vertex AI init 등)는 load() / retrieve() 내부에서
지연 임포트하여 uvicorn 포트 바인딩 전에 실행되지 않도록 한다.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

TOP_K = 20
RRF_K = 60
# pgvector <=> 는 (1 - cosine_similarity) 를 반환한다.
# MIN_COSINE_SIMILARITY = 0.2 이면 최대 허용 distance = 0.8
_MIN_SIM = 0.2
_MAX_DIST = round(1.0 - _MIN_SIM, 6)  # 0.8


class RetrievalService:
    def __init__(self) -> None:
        self._corpus: dict | None = None

    # ------------------------------------------------------------------ #
    # 공개 상태 API                                                        #
    # ------------------------------------------------------------------ #

    @property
    def is_ready(self) -> bool:
        """코퍼스 로드 완료 여부."""
        return self._corpus is not None

    @property
    def corpus(self) -> dict:
        if self._corpus is None:
            raise RuntimeError("RetrievalService.load()가 아직 실행되지 않았습니다.")
        return self._corpus

    # ------------------------------------------------------------------ #
    # 초기화 (서버 시작 시 1회)                                            #
    # ------------------------------------------------------------------ #

    def load(self) -> None:
        """DB에서 BM25 코퍼스를 로드하고 인덱스를 구축한다.

        Dense 임베딩은 쿼리 시 pgvector에 위임하므로 여기서 로드하지 않는다.
        """
        from rank_bm25 import BM25Okapi

        from pipeline.retrieval.bm25_retrieval import (
            load_case_law_from_db,
            load_law_child_from_db,
            tokenize,
        )

        log.info("▶ BM25 코퍼스 로드 시작...")

        law_df = load_law_child_from_db()
        prec_df = load_case_law_from_db()

        law_docs = [
            {"clause_key": str(r["clause_key"]), "text": str(r["child_text"] or "")}
            for _, r in law_df.iterrows()
        ]
        prec_docs = [
            {"case_number": str(r["case_number"]), "text": str(r.get("bm25_target") or "")}
            for _, r in prec_df.iterrows()
        ]

        log.info(
            "  BM25 인덱스 구축 중 (법령 %d건, 판례 %d건)...",
            len(law_docs),
            len(prec_docs),
        )
        law_bm25 = BM25Okapi([tokenize(d["text"]) for d in law_docs])
        prec_bm25 = BM25Okapi([tokenize(d["text"]) for d in prec_docs])

        self._corpus = {
            "law_docs": law_docs,
            "law_bm25": law_bm25,
            "prec_docs": prec_docs,
            "prec_bm25": prec_bm25,
        }
        log.info("▶ BM25 코퍼스 로드 완료 (Dense 검색은 쿼리 시 pgvector에 위임)")

    # ------------------------------------------------------------------ #
    # Dense 검색 (pgvector)                                               #
    # ------------------------------------------------------------------ #

    def _pgvector_search(
        self,
        query_vec,  # np.ndarray
        top_k: int,
    ) -> dict[str, tuple[int, str]]:
        """pgvector <=> (코사인 거리)로 법령·판례를 각각 검색한다.

        반환값: {doc_id: (rank, source_type)}
          - doc_id  : clause_key(법령) 또는 case_number(판례) 문자열
          - rank    : 1-based 순위 (거리 오름차순)
          - source_type: "law" | "precedent"

        vec_literal은 numpy float 값만으로 구성된 문자열이므로 SQL 인젝션 위험 없음.
        pg8000 드라이버는 pgvector 타입 어댑터를 지원하지 않아 문자열 리터럴로 캐스팅한다.
        """
        from sqlalchemy import text

        from shared.db.connection import get_db_client

        # numpy ndarray → '[f0,f1,...,fn]' 문자열
        vec_literal = "[" + ",".join(str(float(x)) for x in query_vec) + "]"
        max_dist = _MAX_DIST

        db = get_db_client()

        law_rows = db.fetch_all(
            text(f"""
                SELECT clause_key::text AS doc_id
                FROM   law_child
                WHERE  embed_vertex IS NOT NULL
                  AND  embed_vertex <=> '{vec_literal}'::vector <= {max_dist}
                ORDER BY embed_vertex <=> '{vec_literal}'::vector
                LIMIT  :top_k
            """),
            {"top_k": top_k},
        )

        prec_rows = db.fetch_all(
            text(f"""
                SELECT case_number::text AS doc_id
                FROM   case_law
                WHERE  embed_vertex IS NOT NULL
                  AND  embed_vertex <=> '{vec_literal}'::vector <= {max_dist}
                ORDER BY embed_vertex <=> '{vec_literal}'::vector
                LIMIT  :top_k
            """),
            {"top_k": top_k},
        )

        hits: dict[str, tuple[int, str]] = {}
        for rank, row in enumerate(law_rows, 1):
            hits[str(row["doc_id"])] = (rank, "law")
        for rank, row in enumerate(prec_rows, 1):
            doc_id = str(row["doc_id"])
            # 동일 doc_id가 두 테이블에 겹칠 일은 없지만 방어적으로 처리
            if doc_id not in hits or rank < hits[doc_id][0]:
                hits[doc_id] = (rank, "precedent")

        log.debug(
            "  pgvector 결과: 법령 %d건, 판례 %d건",
            len(law_rows),
            len(prec_rows),
        )
        return hits

    # ------------------------------------------------------------------ #
    # 하이브리드 검색 (BM25 + Dense → RRF)                                #
    # ------------------------------------------------------------------ #

    def retrieve(self, payload: dict) -> dict:
        """BM25 → Dense(pgvector) → RRF 실행.

        Parameters
        ----------
        payload:
            build_retrieval_payload() 결과.
            필수 키: "bm25_keywords" (list[str]), "dense_query" (str)

        Returns
        -------
        dict with keys:
            "bm25"  : BM25 순위 목록
            "dense" : Dense 순위 목록
            "rrf"   : RRF 융합 순위 목록
        각 항목: {"doc_id", "source_type", "rank", ...}
        """
        from pipeline.retrieval.bm25_retrieval import build_query_tokens
        from pipeline.retrieval.dense_retrieval import embed_query

        corpus = self.corpus

        # ── BM25 ──────────────────────────────────────────────────────
        query_tokens = build_query_tokens(payload["bm25_keywords"])
        bm25_hits: dict[str, tuple[int, str]] = {}
        for docs, bm25, source_type, id_field in [
            (corpus["law_docs"], corpus["law_bm25"], "law", "clause_key"),
            (corpus["prec_docs"], corpus["prec_bm25"], "precedent", "case_number"),
        ]:
            scores = bm25.get_scores(query_tokens)
            top_idx = sorted(
                range(len(scores)), key=lambda i: scores[i], reverse=True
            )[:TOP_K]
            for rank, idx in enumerate(top_idx, 1):
                bm25_hits[docs[idx][id_field]] = (rank, source_type)

        # ── Dense (pgvector) ──────────────────────────────────────────
        query_vec = embed_query(payload["dense_query"], "embed_vertex")
        dense_hits = self._pgvector_search(query_vec, TOP_K)

        # ── RRF ───────────────────────────────────────────────────────
        scored = []
        for doc_id in set(bm25_hits) | set(dense_hits):
            b_rank = bm25_hits[doc_id][0] if doc_id in bm25_hits else 1000
            d_rank = dense_hits[doc_id][0] if doc_id in dense_hits else 1000
            source_type = (bm25_hits.get(doc_id) or dense_hits.get(doc_id))[1]
            scored.append(
                {
                    "doc_id": doc_id,
                    "source_type": source_type,
                    "rrf_score": round(
                        1 / (RRF_K + b_rank) + 1 / (RRF_K + d_rank), 6
                    ),
                    "bm25_rank": b_rank if b_rank != 1000 else None,
                    "dense_rank": d_rank if d_rank != 1000 else None,
                }
            )

        scored.sort(
            key=lambda x: (
                -x["rrf_score"],
                x["bm25_rank"] if x["bm25_rank"] is not None else 1000,
                x["dense_rank"] if x["dense_rank"] is not None else 1000,
                x["doc_id"],
            )
        )
        rrf_results = scored[:TOP_K]
        for rank, item in enumerate(rrf_results, 1):
            item["rank"] = rank

        bm25_results = sorted(
            [
                {"doc_id": d, "source_type": st, "rank": r}
                for d, (r, st) in bm25_hits.items()
            ],
            key=lambda x: x["rank"],
        )
        dense_results = sorted(
            [
                {"doc_id": d, "source_type": st, "rank": r}
                for d, (r, st) in dense_hits.items()
            ],
            key=lambda x: x["rank"],
        )

        return {"bm25": bm25_results, "dense": dense_results, "rrf": rrf_results}


retrieval_service = RetrievalService()
