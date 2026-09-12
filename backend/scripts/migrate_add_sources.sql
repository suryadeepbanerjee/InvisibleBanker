-- ================================================================
-- INVISIBLE BANKER — Add Sources Registry Table
-- Run this in Supabase SQL Editor AFTER schema.sql
-- ================================================================

-- ─── Sources Registry ─────────────────────────────────────────────
-- Tracks all financial information sources: banks, regulators, government portals.
-- crawl_enabled = true ONLY for P0 approved sources (12 total as of 2026-09-11).
-- All others are stored as metadata only and NOT crawled until P0 is demo-solid.

CREATE TABLE IF NOT EXISTS sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    category TEXT NOT NULL,         -- bank_psb | bank_private | sfb | rrb | payments_bank | foreign_bank | cooperative | government | regulatory | insurance | pension | securities | msme | npci
    authority_level INTEGER NOT NULL, -- 1=regulator, 2=government, 3=official_bank, 4=secondary, 5=reference_only
    base_url TEXT NOT NULL,
    crawl_enabled BOOLEAN DEFAULT false,   -- P0 approved sources only
    product_data BOOLEAN DEFAULT false,    -- has loan/deposit/card products
    regulatory_data BOOLEAN DEFAULT false, -- has regulations/circulars
    scheme_data BOOLEAN DEFAULT false,     -- has government schemes
    document_data BOOLEAN DEFAULT false,   -- has document/identity info
    crawl_subpaths TEXT[] DEFAULT '{}',    -- specific subpaths to crawl within base_url
    crawl_exclude_patterns TEXT[] DEFAULT '{}', -- URL patterns to skip
    refresh_days INTEGER DEFAULT 30,       -- how often to re-crawl (days)
    last_crawled TIMESTAMPTZ,
    last_crawl_status TEXT,               -- SUCCESS | CACHED_REAL | BLOCKED | UNAVAILABLE | PENDING
    chunks_count INTEGER DEFAULT 0,       -- how many knowledge chunks from this source
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS sources_crawl_enabled_idx ON sources (crawl_enabled) WHERE crawl_enabled = true;
CREATE INDEX IF NOT EXISTS sources_category_idx ON sources (category);

-- ─── Verification ─────────────────────────────────────────────────
SELECT COUNT(*) as total_sources,
       COUNT(*) FILTER (WHERE crawl_enabled = true) as p0_enabled
FROM sources;
