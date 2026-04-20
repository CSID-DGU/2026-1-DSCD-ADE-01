CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS law_parent (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    article_key TEXT NOT NULL UNIQUE,
    law_name TEXT NOT NULL,
    law_abbr TEXT,
    ministry TEXT NOT NULL,
    enforcement_date DATE NOT NULL,
    article_no TEXT NOT NULL,
    article_title TEXT,
    article_date DATE NOT NULL,
    is_amended BOOLEAN NOT NULL DEFAULT FALSE,
    is_deleted BOOLEAN NOT NULL DEFAULT FALSE,
    parent_text TEXT NOT NULL,
    is_article_only BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS law_child (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    clause_key TEXT NOT NULL UNIQUE,
    article_key TEXT NOT NULL,
    parent_id BIGINT NOT NULL REFERENCES law_parent(id) ON DELETE CASCADE,
    law_name TEXT NOT NULL,
    article_no TEXT NOT NULL,
    paragraph_no INTEGER,
    child_text TEXT NOT NULL,
    embed_vertex vector(3072),
    embed_kure vector(1024)
);

CREATE INDEX IF NOT EXISTS idx_law_parent_law_article
    ON law_parent (law_name, article_no);

CREATE INDEX IF NOT EXISTS idx_law_parent_is_deleted
    ON law_parent (is_deleted);

CREATE INDEX IF NOT EXISTS idx_law_child_article_key
    ON law_child (article_key);

CREATE INDEX IF NOT EXISTS idx_law_child_parent_id
    ON law_child (parent_id);
