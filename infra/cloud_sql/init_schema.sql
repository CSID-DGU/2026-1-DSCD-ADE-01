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
    embed_kure vector(1024),
    embed_e5 vector(1024)
);

CREATE INDEX IF NOT EXISTS idx_law_parent_law_article
    ON law_parent (law_name, article_no);

CREATE INDEX IF NOT EXISTS idx_law_parent_is_deleted
    ON law_parent (is_deleted);

CREATE INDEX IF NOT EXISTS idx_law_child_article_key
    ON law_child (article_key);

CREATE INDEX IF NOT EXISTS idx_law_child_parent_id
    ON law_child (parent_id);

CREATE TABLE IF NOT EXISTS case_law (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_id TEXT NOT NULL UNIQUE,
    case_name TEXT,
    case_number TEXT,
    judgment_date DATE,
    judgment_result TEXT,
    court_name TEXT,
    court_type_code INTEGER,
    judgment_type TEXT,
    issue TEXT,
    judgment_summary TEXT,
    referenced_law TEXT,
    referenced_case TEXT,
    case_detail TEXT,
    embed_vertex vector(3072),
    embed_kure vector(1024),
    embed_e5 vector(1024)
);

ALTER TABLE law_child
    ADD COLUMN IF NOT EXISTS embed_vertex vector(3072);

ALTER TABLE law_child
    ADD COLUMN IF NOT EXISTS embed_kure vector(1024);

ALTER TABLE case_law
    ADD COLUMN IF NOT EXISTS embed_vertex vector(3072);

ALTER TABLE case_law
    ADD COLUMN IF NOT EXISTS embed_kure vector(1024);

ALTER TABLE law_child
    ADD COLUMN IF NOT EXISTS embed_e5 vector(1024);

ALTER TABLE case_law
    ADD COLUMN IF NOT EXISTS embed_e5 vector(1024);

CREATE INDEX IF NOT EXISTS idx_case_law_case_number
    ON case_law (case_number);

CREATE INDEX IF NOT EXISTS idx_case_law_judgment_date
    ON case_law (judgment_date);

CREATE INDEX IF NOT EXISTS idx_case_law_court_name
    ON case_law (court_name);

CREATE TABLE IF NOT EXISTS referenced_law (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES case_law(case_id) ON DELETE CASCADE,
    clause_key TEXT NOT NULL,
    law_name TEXT NOT NULL,
    article_no TEXT NOT NULL,
    paragraph_no TEXT,
    parent_id BIGINT REFERENCES law_parent(id),
    child_id BIGINT REFERENCES law_child(id),
    CONSTRAINT uq_referenced_law_case_clause UNIQUE (case_id, clause_key)
);

CREATE INDEX IF NOT EXISTS idx_referenced_law_case_id
    ON referenced_law (case_id);

CREATE INDEX IF NOT EXISTS idx_referenced_law_clause_key
    ON referenced_law (clause_key);

CREATE INDEX IF NOT EXISTS idx_referenced_law_parent_id
    ON referenced_law (parent_id);

CREATE INDEX IF NOT EXISTS idx_referenced_law_child_id
    ON referenced_law (child_id);

CREATE TABLE IF NOT EXISTS referenced_case (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES case_law(case_id) ON DELETE CASCADE,
    referenced_case_number TEXT NOT NULL,
    CONSTRAINT uq_referenced_case_case_number UNIQUE (case_id, referenced_case_number)
);

CREATE INDEX IF NOT EXISTS idx_referenced_case_case_id
    ON referenced_case (case_id);

CREATE INDEX IF NOT EXISTS idx_referenced_case_number
    ON referenced_case (referenced_case_number);

CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY,
    title VARCHAR,
    body TEXT,
    tags JSONB,
    written_at DATE,
    embedding vector(3072)
);

ALTER TABLE questions
    ALTER COLUMN embedding TYPE vector(3072);

CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    lawyer_name VARCHAR,
    answer_body JSONB,
    written_at DATE,
    dispute_background TEXT,
    lawyer_conclusion TEXT,
    lawyer_reasoning TEXT,
    action_checklist TEXT
);

CREATE INDEX IF NOT EXISTS idx_answers_question_id
    ON answers (question_id);

CREATE TABLE IF NOT EXISTS answer_referenced_law (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    answer_id INTEGER NOT NULL REFERENCES answers(id) ON DELETE CASCADE,
    clause_key TEXT NOT NULL,
    law_name TEXT NOT NULL,
    article_no TEXT NOT NULL,
    paragraph_no TEXT,
    parent_id BIGINT REFERENCES law_parent(id),
    child_id BIGINT REFERENCES law_child(id),
    CONSTRAINT uq_answer_referenced_law_answer_clause UNIQUE (answer_id, clause_key)
);

CREATE INDEX IF NOT EXISTS idx_answer_referenced_law_answer_id
    ON answer_referenced_law (answer_id);

CREATE INDEX IF NOT EXISTS idx_answer_referenced_law_clause_key
    ON answer_referenced_law (clause_key);

CREATE INDEX IF NOT EXISTS idx_answer_referenced_law_parent_id
    ON answer_referenced_law (parent_id);

CREATE INDEX IF NOT EXISTS idx_answer_referenced_law_child_id
    ON answer_referenced_law (child_id);

CREATE TABLE IF NOT EXISTS answer_referenced_case (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    answer_id INTEGER NOT NULL REFERENCES answers(id) ON DELETE CASCADE,
    referenced_case_number TEXT NOT NULL,
    CONSTRAINT uq_answer_referenced_case_answer_number
        UNIQUE (answer_id, referenced_case_number)
);

CREATE INDEX IF NOT EXISTS idx_answer_referenced_case_answer_id
    ON answer_referenced_case (answer_id);

CREATE INDEX IF NOT EXISTS idx_answer_referenced_case_number
    ON answer_referenced_case (referenced_case_number);
