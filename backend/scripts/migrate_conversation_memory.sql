-- ================================================================
-- INVISIBLE BANKER — Conversation Memory Migration
-- Run in Supabase SQL Editor → New Query → Run
-- ================================================================

-- ─── Conversations ────────────────────────────────────────────
-- One conversation per user session. Persistent across page refreshes.
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    -- Rolling summary of what has been established so far
    summary JSONB DEFAULT '{}',
    -- Current workflow intent (not the same as application workflow state)
    current_intent TEXT DEFAULT 'unknown',
    -- Language preference detected from the conversation
    language TEXT DEFAULT 'en-IN',
    -- Research state: IDLE, ANALYZING, RESEARCHING, READY, FAILED
    research_status TEXT DEFAULT 'IDLE',
    -- ID of the latest research job for this conversation
    latest_research_job_id UUID,
    -- Whether this is an active conversation (not explicitly closed)
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Messages ─────────────────────────────────────────────────
-- Every message in a conversation. Used for history retrieval.
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    language TEXT DEFAULT 'en-IN',
    -- Additional metadata: intent, source_type, research_used, etc.
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Research Jobs ────────────────────────────────────────────
-- Tracks async live research jobs triggered during conversations.
CREATE TABLE IF NOT EXISTS research_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    -- The classified intent that triggered this research
    intent TEXT NOT NULL,
    -- The user query that triggered it
    query TEXT NOT NULL,
    -- Source categories that were routed to (e.g., ["bank", "msme", "govt_scheme"])
    source_categories TEXT[] DEFAULT '{}',
    -- Status: QUEUED, CRAWLING, EMBEDDING, COMPLETE, FAILED
    status TEXT DEFAULT 'QUEUED',
    -- Number of pages discovered
    pages_discovered INTEGER DEFAULT 0,
    -- Number of pages crawled
    pages_crawled INTEGER DEFAULT 0,
    -- Number of knowledge chunks created
    chunks_created INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Indexes for performance ──────────────────────────────────
-- Fast message retrieval per conversation ordered by time
CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
    ON messages(conversation_id, created_at DESC);

-- Fast conversation lookup per user (for session recovery)
CREATE INDEX IF NOT EXISTS idx_conversations_user_active
    ON conversations(user_id, is_active, updated_at DESC);

-- Fast research job lookup per conversation
CREATE INDEX IF NOT EXISTS idx_research_jobs_conversation
    ON research_jobs(conversation_id, created_at DESC);

-- ─── RLS ─────────────────────────────────────────────────────
-- Backend uses service_role which bypasses RLS.
-- Enabling RLS so user-level access can be added later (production).
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_jobs ENABLE ROW LEVEL SECURITY;

-- ─── Verification ─────────────────────────────────────────────
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('conversations', 'messages', 'research_jobs')
ORDER BY table_name;
