"""임대차 특약 query expansion 패키지 (메인·기본 진입점).

구조화된 expansion_query(네 섹션) + keywords 스키마를 쓴다.
이전 단순 스키마 실험은 ``pipeline.retrieval.query_expansion_v1`` 을 본다.
"""

from pipeline.retrieval.query_expansion.query_expansion import (
    QueryExpansionError,
    build_repair_prompt,
    expand_clause,
)
from pipeline.retrieval.query_expansion.query_expansion_prompt import (
    SYSTEM_PROMPT,
    build_user_prompt,
)
from pipeline.retrieval.query_expansion.query_expansion_schema import (
    ClauseQueryExpansion,
)
from pipeline.retrieval.query_expansion.retrieval_adapter import (
    build_retrieval_payload,
)

__all__ = [
    "ClauseQueryExpansion",
    "QueryExpansionError",
    "SYSTEM_PROMPT",
    "build_repair_prompt",
    "build_retrieval_payload",
    "build_user_prompt",
    "expand_clause",
]
