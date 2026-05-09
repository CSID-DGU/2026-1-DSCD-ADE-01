export type ClauseQueryExpansion = {
  expansion_query: string;
  keywords: string[];
};

export type SpecialTermExpansionResult = {
  index?: number;
  special_term: string;
  expansion: ClauseQueryExpansion;
  retrieval_payload?: Record<string, unknown>;
};

export type AnalyzeContractApiResponse = {
  contract: {
    lease_type?: string;
    property_info?: {
      address?: string | null;
      building?: {
        use?: string | null;
        structure?: string | null;
      } | null;
      leased_part?: {
        detail_address?: string | null;
      } | null;
      contract_kind?: {
        type?: string | null;
      } | null;
      prior_fixdate?: string | null;
      tax_arrears?: string | null;
    };
    general_terms?: Record<
      string,
      {
        text?: string | null;
        details?: Record<string, unknown> | null;
      } | null
    >;
    special_terms?: string[];
  };
  special_term_expansions: SpecialTermExpansionResult[];
};

export type ClauseRiskLevel = "낮음" | "주의" | "위험" | "위법가능" | "판단불가";
