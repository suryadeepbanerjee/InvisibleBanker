-- ================================================================
-- INVISIBLE BANKER — Supabase Database Schema
-- Run this in the Supabase SQL Editor:
-- Dashboard → SQL Editor → New Query → Paste and Run
-- ================================================================

-- Enable pgvector extension (required for semantic search)
CREATE EXTENSION IF NOT EXISTS vector;

-- ─── Users ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT,
    language TEXT DEFAULT 'en-IN',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Profiles (progressive profile building) ───────────────────────
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    structured_profile JSONB DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Documents (uploaded financial documents) ──────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    type TEXT,
    storage_path TEXT,
    extracted_text TEXT,
    extracted_json JSONB DEFAULT '{}',
    confidence FLOAT DEFAULT 0,
    status TEXT DEFAULT 'pending',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Knowledge base (RAG source chunks with embeddings) ──────────────
CREATE TABLE IF NOT EXISTS knowledge (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    authority TEXT NOT NULL,
    source_url TEXT,
    source_type TEXT,
    content TEXT NOT NULL,
    embedding vector(384),          -- paraphrase-multilingual-MiniLM-L12-v2 dimension
    version INTEGER DEFAULT 1,
    content_hash TEXT,
    effective_date DATE,
    last_checked TIMESTAMPTZ DEFAULT NOW(),
    page_number INTEGER,
    metadata JSONB DEFAULT '{}'
);

-- ─── Sources Registry (added in Phase 2) ──────────────────────────
CREATE TABLE IF NOT EXISTS sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    authority_level INTEGER NOT NULL,
    base_url TEXT NOT NULL,
    crawl_enabled BOOLEAN DEFAULT false,
    product_data BOOLEAN DEFAULT false,
    regulatory_data BOOLEAN DEFAULT false,
    scheme_data BOOLEAN DEFAULT false,
    document_data BOOLEAN DEFAULT false,
    crawl_subpaths TEXT[] DEFAULT '{}',
    crawl_exclude_patterns TEXT[] DEFAULT '{}',
    refresh_days INTEGER DEFAULT 30,
    last_crawled TIMESTAMPTZ,
    last_crawl_status TEXT,
    chunks_count INTEGER DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Products (financial products/schemes with JSON eligibility rules) ─
CREATE TABLE IF NOT EXISTS products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    rules JSONB DEFAULT '[]',
    required_documents JSONB DEFAULT '[]',
    source_metadata JSONB DEFAULT '{}',
    min_amount FLOAT,
    max_amount FLOAT,
    active_version INTEGER DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Applications (workflow state machine + audit trail) ─────────────
CREATE TABLE IF NOT EXISTS applications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    selected_product_id UUID REFERENCES products(id),
    workflow_state TEXT DEFAULT 'START',
    eligibility_result JSONB DEFAULT '{}',
    evidence JSONB DEFAULT '{}',
    audit_events JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Vector similarity search function ────────────────────────────────
CREATE OR REPLACE FUNCTION match_knowledge_chunks(
    query_embedding vector(384),
    match_count INT DEFAULT 5,
    authority_filter TEXT[] DEFAULT NULL
)
RETURNS TABLE (
    id UUID,
    title TEXT,
    authority TEXT,
    source_url TEXT,
    content TEXT,
    page_number INTEGER,
    last_checked TIMESTAMPTZ,
    version INTEGER,
    metadata JSONB,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        k.id,
        k.title,
        k.authority,
        k.source_url,
        k.content,
        k.page_number,
        k.last_checked,
        k.version,
        k.metadata,
        1 - (k.embedding <=> query_embedding) AS similarity
    FROM knowledge k
    WHERE
        (authority_filter IS NULL OR k.authority = ANY(authority_filter))
        AND k.embedding IS NOT NULL
    ORDER BY k.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- ─── Index for faster vector search ────────────────────────────────────
-- Note: Run AFTER inserting at least some rows for IVFFlat to work
-- CREATE INDEX IF NOT EXISTS knowledge_embedding_idx
-- ON knowledge USING ivfflat (embedding vector_cosine_ops)
-- WITH (lists = 100);

-- ─── Row Level Security (basic setup) ──────────────────────────────────
-- Enable RLS on sensitive tables
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE applications ENABLE ROW LEVEL SECURITY;

-- Note: For hackathon demo, the backend uses service_role key which bypasses RLS.
-- In production, add proper JWT-based policies.

-- ─── Storage bucket setup ──────────────────────────────────────────────
-- Run in Supabase Dashboard → Storage → Create bucket:
-- Name: financial-documents
-- Public: NO (private)
-- Then add this policy to allow backend access via service role (automatic).

-- ================================================================
-- VERIFICATION QUERY (run after setup to confirm everything works)
-- ================================================================
SELECT 
    table_name, 
    (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = t.table_name) as columns
FROM information_schema.tables t
WHERE table_schema = 'public' 
AND table_name IN ('users', 'profiles', 'documents', 'knowledge', 'products', 'applications')
ORDER BY table_name;
