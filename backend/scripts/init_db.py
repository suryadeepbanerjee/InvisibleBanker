"""
Database initialization script.

Creates all required tables in Supabase and enables pgvector.

Run once: python scripts/init_db.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from app.core.database import get_supabase_admin

INIT_SQL = """
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT,
    language TEXT DEFAULT 'en-IN',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Profiles table (progressive profile building)
CREATE TABLE IF NOT EXISTS profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE UNIQUE,
    structured_profile JSONB DEFAULT '{}',
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Documents table
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

-- Knowledge base table (RAG source chunks)
CREATE TABLE IF NOT EXISTS knowledge (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    authority TEXT NOT NULL,
    source_url TEXT,
    source_type TEXT,
    content TEXT NOT NULL,
    embedding vector(384),
    version INTEGER DEFAULT 1,
    content_hash TEXT,
    effective_date DATE,
    last_checked TIMESTAMPTZ DEFAULT NOW(),
    page_number INTEGER,
    metadata JSONB DEFAULT '{}'
);

-- Products table (financial products/schemes with rules)
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

-- Applications table (workflow state machine)
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

-- Vector similarity search function
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

-- Index for faster vector search
CREATE INDEX IF NOT EXISTS knowledge_embedding_idx 
ON knowledge USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);
"""


def main():
    print("Initializing Invisible Banker database...")
    db = get_supabase_admin()

    # Execute SQL via Supabase RPC or direct query
    # Note: Supabase Python client doesn't support raw SQL directly
    # These DDL statements should be run in the Supabase SQL Editor
    print("\n" + "="*60)
    print("IMPORTANT: Run the following SQL in your Supabase SQL Editor:")
    print("Dashboard -> SQL Editor -> New Query -> Paste and Run")
    print("="*60)
    print(INIT_SQL)
    print("="*60)
    print("\nAlternatively, use the Supabase CLI:")
    print("supabase db push")

    # Verify connection
    try:
        res = db.table("users").select("id").limit(1).execute()
        print("\nOK: Connected to Supabase successfully!")
        print("If tables don't exist yet, run the SQL above first.")
    except Exception as e:
        print(f"\nERROR: Supabase connection error: {e}")
        print("Check your SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env")
        print("IMPORTANT: Run schema.sql in Supabase SQL Editor first!")
        sys.exit(1)


if __name__ == "__main__":
    main()
