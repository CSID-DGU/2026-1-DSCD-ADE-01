"use client";

type Article = {
  title: string;
  items: string[];
};

type DocumentPanelProps = {
  contractTitle?: string;
  articles: Article[];
};

function ArticleBlock({ article }: { article: Article }) {
  return (
    <div className="flex flex-col gap-[5px] pt-4">
      <p
        className="text-sm font-bold"
        style={{ color: "#1A1C1E", fontFamily: "var(--font-public-sans)", lineHeight: "23px" }}
      >
        {article.title}
      </p>
      {article.items.map((text, i) => (
        <div
          key={i}
          className="px-0 py-[10px]"
          style={{
            paddingLeft: "24px",
            border: "1px solid #E5EAF1",
          }}
        >
          <p
            className="text-sm"
            style={{ color: "#1A1C1E", fontFamily: "var(--font-public-sans)", lineHeight: "23px" }}
          >
            {text}
          </p>
        </div>
      ))}
    </div>
  );
}

export function DocumentPanel({ contractTitle, articles }: DocumentPanelProps) {
  return (
    <section
      className="flex flex-col overflow-y-auto"
      style={{
        width: "640px",
        background: "#FFFFFF",
        borderRight: "1px solid #C4C6CF",
        padding: "32px 32px 128px",
        flexShrink: 0,
      }}
    >
      {/* Document title */}
      <div
        className="flex flex-col items-center gap-[8px] pb-6"
        style={{ borderBottom: "1px solid #E2E8F0" }}
      >
        <h2
          className="text-lg font-semibold text-center"
          style={{
            color: "#1A1C1E",
            fontFamily: "var(--font-public-sans)",
            letterSpacing: "1.8px",
            textTransform: "uppercase",
          }}
        >
          {contractTitle ?? "표준 주택임대차계약서"}
        </h2>
        <p
          className="text-sm text-center"
          style={{ color: "#43474E", fontFamily: "var(--font-public-sans)" }}
        >
          Standard Residential Lease Agreement
        </p>
      </div>

      {/* Articles */}
      <div className="flex flex-col gap-[15px]">
        {articles.map((article, i) => (
          <ArticleBlock key={i} article={article} />
        ))}
      </div>
    </section>
  );
}
