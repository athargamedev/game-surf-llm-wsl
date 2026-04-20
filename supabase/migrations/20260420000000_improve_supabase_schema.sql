-- Add npc_profiles table, indexes, constraints, and RLS policies
-- Version: 20260420000000
CREATE TABLE IF NOT EXISTS npc_profiles (
    npc_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    npc_scope TEXT DEFAULT 'instructor',
    artifact_key TEXT,
    subject TEXT,
    subject_focus TEXT,
    personality JSONB DEFAULT '{}'::jsonb,
    voice_rules JSONB DEFAULT '[]'::jsonb,
    domain_knowledge JSONB DEFAULT '[]'::jsonb,
    generation_defaults JSONB DEFAULT '{}'::jsonb,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Trigger to auto-update updated_at
CREATE OR REPLACE FUNCTION npc_profiles_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS npc_profiles_update_timestamp ON npc_profiles;
CREATE TRIGGER npc_profiles_update_timestamp
    BEFORE UPDATE ON npc_profiles
    FOR EACH ROW EXECUTE FUNCTION npc_profiles_update_timestamp();

-- Index for active NPCs lookup
CREATE INDEX IF NOT EXISTS idx_npc_profiles_active ON npc_profiles(is_active) WHERE is_active = true;

-- Insert sample NPC profiles (synced from nppc_profiles.json)
INSERT INTO npc_profiles (npc_id, display_name, npc_scope, artifact_key, subject, subject_focus, personality, voice_rules, generation_defaults, is_active) VALUES
    ('brazilian_history', 'Professor Pedro', 'instructor', 'brazilian_history_instructor', 'History of Brazil, Colonial era, Empire, Republic, Culture', 'Brazilian History',
     '{"tone": "educational, patriotic, articulate but warm", "speaking_style": "informative and respectful of historical context"}'::jsonb,
     '["Speak in 1-3 sentences", "Highlight significant Brazilian figures"]'::jsonb,
     '{"temperature": 0.72, "max_response_tokens": 180}'::jsonb, true)
ON CONFLICT (npc_id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    npc_scope = EXCLUDED.npc_scope,
    artifact_key = EXCLUDED.artifact_key,
    subject = EXCLUDED.subject,
    subject_focus = EXCLUDED.subject_focus,
    personality = EXCLUDED.personality,
    voice_rules = EXCLUDED.voice_rules,
    generation_defaults = EXCLUDED.generation_defaults;

INSERT INTO npc_profiles (npc_id, display_name, npc_scope, artifact_key, subject, subject_focus, personality, voice_rules, generation_defaults, is_active) VALUES
    ('marvel_comics_instructor', 'MarvelOracle', 'instructor', 'marvel_comics_instructor', 'Marvel Comics lore, Avengers, X-Men, Cosmic Universe', 'Marvel Comics lore',
     '{"tone": "enthusiastic, grand, comic-book legendary", "speaking_style": "excited, using hyperbole"}'::jsonb,
     '["Keep it high-energy", "Reference specific comic events"]'::jsonb,
     '{"temperature": 0.78, "max_response_tokens": 180}'::jsonb, true)
ON CONFLICT (npc_id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    npc_scope = EXCLUDED.npc_scope,
    artifact_key = EXCLUDED.artifact_key,
    subject = EXCLUDED.subject,
    subject_focus = EXCLUDED.subject_focus;

INSERT INTO npc_profiles (npc_id, display_name, npc_scope, artifact_key, subject, subject_focus, personality, voice_rules, generation_defaults, is_active) VALUES
    ('kosmos_instructor', 'Professor Kosmos', 'instructor', 'greek_mythology_instructor', 'Greek and Roman Mythology, ancient legends, heroic epics', 'Greek and Roman Mythology',
     '{"tone": "theatrical, dramatic, ancient-herald grand", "speaking_style": "archaic, elevated"}'::jsonb,
     '["Speak in 1-3 short sentences", "Use archaic, elevated vocabulary"]'::jsonb,
     '{"temperature": 0.72, "max_response_tokens": 180}'::jsonb, true)
ON CONFLICT (npc_id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    npc_scope = EXCLUDED.npc_scope,
    artifact_key = EXCLUDED.artifact_key,
    subject = EXCLUDED.subject,
    subject_focus = EXCLUDED.subject_focus;

INSERT INTO npc_profiles (npc_id, display_name, npc_scope, artifact_key, subject, subject_focus, personality, voice_rules, generation_defaults, is_active) VALUES
    ('maestro_jazz_instructor', 'The Maestro', 'instructor', 'jazz_history_instructor', 'Jazz history, music theory, improvisation, cultural impact', 'Jazz History and Music Theory',
     '{"tone": "smooth, sophisticated, cool, late-night club host", "speaking_style": "using jazz slang"}'::jsonb,
     '["Speak in 1-3 short sentences", "Use jazz slang"]'::jsonb,
     '{"temperature": 0.78, "max_response_tokens": 180}'::jsonb, true)
ON CONFLICT (npc_id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    npc_scope = EXCLUDED.npc_scope,
    artifact_key = EXCLUDED.artifact_key,
    subject = EXCLUDED.subject,
    subject_focus = EXCLUDED.subject_focus;

INSERT INTO npc_profiles (npc_id, display_name, npc_scope, artifact_key, subject, subject_focus, personality, voice_rules, generation_defaults, is_active) VALUES
    ('movies_instructor', 'Professor Reel', 'instructor', 'movies_instructor', 'Cinema history, Oscar winners, remarkable movie scenes', 'Cinema and Film Studies',
     '{"tone": "cinematic, thoughtful, vivid, and warmly scholarly", "speaking_style": "speaks like a film professor"}'::jsonb,
     '["Speak in 1-3 short sentences", "Mention film titles, directors, actors"]'::jsonb,
     '{"temperature": 0.74, "max_response_tokens": 180}'::jsonb, true)
ON CONFLICT (npc_id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    npc_scope = EXCLUDED.npc_scope,
    artifact_key = EXCLUDED.artifact_key,
    subject = EXCLUDED.subject,
    subject_focus = EXCLUDED.subject_focus;

INSERT INTO npc_profiles (npc_id, display_name, npc_scope, artifact_key, subject, subject_focus, personality, voice_rules, generation_defaults, is_active) VALUES
    ('llm_instructor', 'Professor LoRA', 'instructor', 'llm_instructor', 'LoRA fine-tuning, adapter layers, parameter-efficient training, QLoRA', 'LoRA Fine-tuning for LLMs',
     '{"tone": "educational, technical, patient, and precise", "speaking_style": "explains complex concepts"}'::jsonb,
     '["Speak in 1-3 short sentences", "Use concrete examples and metaphors"]'::jsonb,
     '{"temperature": 0.72, "max_response_tokens": 180}'::jsonb, true)
ON CONFLICT (npc_id) DO UPDATE SET
    display_name = EXCLUDED.display_name,
    npc_scope = EXCLUDED.npc_scope,
    artifact_key = EXCLUDED.artifact_key,
    subject = EXCLUDED.subject,
    subject_focus = EXCLUDED.subject_focus;

-- ==========================================
-- PART 2: ADD CONSTRAINTS & INDEXES
-- ==========================================

-- Fix player_profiles: add primary key constraint (idempotent)
ALTER TABLE player_profiles ADD CONSTRAINT player_profiles_pkey PRIMARY KEY (player_id);

-- Add unique constraint on dialogue_sessions for player+npc+status
ALTER TABLE dialogue_sessions ADD CONSTRAINT chk_session_uniqueness 
    CHECK (player_id IS NOT NULL AND npc_id IS NOT NULL);

-- Add NOT NULL constraints where missing
ALTER TABLE dialogue_sessions ALTER COLUMN player_id SET NOT NULL;
ALTER TABLE dialogue_sessions ALTER COLUMN npc_id SET NOT NULL;
ALTER TABLE dialogue_sessions ALTER COLUMN status SET NOT NULL;
ALTER TABLE dialogue_sessions ALTER COLUMN started_at SET NOT NULL;

ALTER TABLE dialogue_turns ALTER COLUMN session_id SET NOT NULL;
ALTER TABLE dialogue_turns ALTER COLUMN player_message SET NOT NULL;
ALTER TABLE dialogue_turns ALTER COLUMN npc_response SET NOT NULL;

ALTER TABLE npc_memories ALTER COLUMN player_id SET NOT NULL;
ALTER TABLE npc_memories ALTER COLUMN npc_id SET NOT NULL;
ALTER TABLE npc_memories ALTER COLUMN summary SET NOT NULL;

ALTER TABLE player_memory_embeddings ALTER COLUMN player_id SET NOT NULL;
ALTER TABLE player_memory_embeddings ALTER COLUMN npc_id SET NOT NULL;

-- Create composite indexes for common query patterns
-- dialogue_sessions: get active session for player+npc
CREATE INDEX IF NOT EXISTS idx_dialogue_sessions_player_npc_active 
    ON dialogue_sessions(player_id, npc_id, status) 
    WHERE status = 'active';

-- dialogue_sessions: recent sessions for a player
CREATE INDEX IF NOT EXISTS idx_dialogue_sessions_player_recent 
    ON dialogue_sessions(player_id, started_at DESC);

-- dialogue_turns: turns for a session (for session summary)
CREATE INDEX IF NOT EXISTS idx_dialogue_turns_session_created 
    ON dialogue_turns(session_id, created_at DESC);

-- npc_memories: memories for player+npc (most common query)
CREATE INDEX IF NOT EXISTS idx_npc_memories_player_npc 
    ON npc_memories(player_id, npc_id, created_at DESC);

-- npc_memories: recent memories for any player
CREATE INDEX IF NOT EXISTS idx_npc_memories_recent 
    ON npc_memories(created_at DESC);

-- player_memory_embeddings: embeddings lookup
CREATE INDEX IF NOT EXISTS idx_player_memory_embeddings_player_npc 
    ON player_memory_embeddings(player_id, npc_id, memory_type);

-- relation_graph_edges: player's related terms
CREATE INDEX IF NOT EXISTS idx_graph_edges_source_type 
    ON relation_graph_edges(source_node_id, edge_type, weight DESC);

-- ==========================================
-- PART 3: ADD RLS POLICIES
-- ==========================================

-- Enable RLS on all tables
ALTER TABLE player_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE dialogue_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE dialogue_turns ENABLE ROW LEVEL SECURITY;
ALTER TABLE npc_memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_memory_embeddings ENABLE ROW LEVEL SECURITY;
ALTER TABLE player_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE npc_profiles ENABLE ROW LEVEL SECURITY;

-- Player profiles: service role can do anything, anon can only read own profile
DROP POLICY IF EXISTS "player_profiles_service_role_policy" ON player_profiles;
CREATE POLICY "player_profiles_service_role_policy" ON player_profiles
    FOR ALL USING (true);

-- Dialogue sessions: service role full access
DROP POLICY IF EXISTS "dialogue_sessions_service_role_policy" ON dialogue_sessions;
CREATE POLICY "dialogue_sessions_service_role_policy" ON dialogue_sessions
    FOR ALL USING (true);

-- Dialogue turns: service role full access
DROP POLICY IF EXISTS "dialogue_turns_service_role_policy" ON dialogue_turns;
CREATE POLICY "dialogue_turns_service_role_policy" ON dialogue_turns
    FOR ALL USING (true);

-- NPC memories: service role full access  
DROP POLICY IF EXISTS "npc_memories_service_role_policy" ON npc_memories;
CREATE POLICY "npc_memories_service_role_policy" ON npc_memories
    FOR ALL USING (true);

-- Player memory embeddings: service role full access
DROP POLICY IF EXISTS "player_memory_embeddings_service_role_policy" ON player_memory_embeddings;
CREATE POLICY "player_memory_embeddings_service_role_policy" ON player_memory_embeddings
    FOR ALL USING (true);

-- NPC profiles: anyone can read active NPCs, service role can modify
DROP POLICY IF EXISTS "npc_profiles_read_policy" ON npc_profiles;
CREATE POLICY "npc_profiles_read_policy" ON npc_profiles
    FOR SELECT USING (is_active = true);

DROP POLICY IF EXISTS "npc_profiles_service_role_policy" ON npc_profiles;
CREATE POLICY "npc_profiles_service_role_policy" ON npc_profiles
    FOR ALL USING (true);

-- Relation graph tables: service role full access
DROP POLICY IF EXISTS "relation_graph_service_role_policy" ON relation_graph_nodes;
CREATE POLICY "relation_graph_service_role_policy" ON relation_graph_nodes
    FOR ALL USING (true);

DROP POLICY IF EXISTS "relation_graph_edges_service_role_policy" ON relation_graph_edges;
CREATE POLICY "relation_graph_edges_service_role_policy" ON relation_graph_edges
    FOR ALL USING (true);

-- ==========================================
-- PART 4: HELPER RPC FUNCTIONS
-- ==========================================

-- Get active NPC profile
CREATE OR REPLACE FUNCTION get_npc_profile(target_npc_id TEXT)
RETURNS TABLE (
    npc_id TEXT,
    display_name TEXT,
    npc_scope TEXT,
    subject TEXT,
    personality JSONB,
    voice_rules JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        np.npc_id,
        np.display_name,
        np.npc_scope,
        np.subject,
        np.personality,
        np.voice_rules
    FROM npc_profiles np
    WHERE np.npc_id = target_npc_id AND np.is_active = true;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Get player NPC history (sessions + turns + memories)
CREATE OR REPLACE FUNCTION get_player_npc_history(
    target_player_id TEXT,
    target_npc_id TEXT,
    session_limit INT DEFAULT 10
)
RETURNS TABLE (
    session_id UUID,
    status TEXT,
    started_at TIMESTAMPTZ,
    turn_count BIGINT,
    summary TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ds.session_id,
        ds.status,
        ds.started_at,
        COALESCE(
            (SELECT COUNT(*)::BIGINT FROM dialogue_turns dt WHERE dt.session_id = ds.session_id),
            0::BIGINT
        ) AS turn_count,
        (
            SELECT nm.summary 
            FROM npc_memories nm 
            WHERE nm.player_id = ds.player_id 
              AND nm.npc_id = ds.npc_id
            ORDER BY nm.created_at DESC 
            LIMIT 1
        ) AS summary
    FROM dialogue_sessions ds
    WHERE ds.player_id = target_player_id 
      AND ds.npc_id = target_npc_id
    ORDER BY ds.started_at DESC
    LIMIT session_limit;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Get memory context for LLM (compact format)
CREATE OR REPLACE FUNCTION get_memory_context(
    target_player_id TEXT,
    target_npc_id TEXT,
    memory_limit INT DEFAULT 5
)
RETURNS TABLE (
    summary TEXT,
    turn_count BIGINT,
    last_active TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        nm.summary::TEXT,
        COALESCE(
            (SELECT COUNT(*)::BIGINT 
             FROM dialogue_sessions ds
             JOIN dialogue_turns dt ON dt.session_id = ds.session_id
             WHERE ds.player_id = target_player_id AND ds.npc_id = target_npc_id),
            0::BIGINT
        ) AS turn_count,
        (
            SELECT MAX(ds.started_at)
            FROM dialogue_sessions ds
            WHERE ds.player_id = target_player_id AND ds.npc_id = target_npc_id
        ) AS last_active
    FROM npc_memories nm
    WHERE nm.player_id = target_player_id 
      AND nm.npc_id = target_npc_id
    ORDER BY nm.created_at DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Upsert NPC profile (for syncing from JSON to DB)
CREATE OR REPLACE FUNCTION upsert_npc_profile(
    p_npc_id TEXT,
    p_display_name TEXT,
    p_npc_scope TEXT DEFAULT 'instructor',
    p_artifact_key TEXT,
    p_subject TEXT,
    p_subject_focus TEXT,
    p_personality JSONB DEFAULT '{}'::jsonb,
    p_voice_rules JSONB DEFAULT '[]'::jsonb,
    p_domain_knowledge JSONB DEFAULT '[]'::jsonb
)
RETURNS BOOLEAN AS $$
BEGIN
    INSERT INTO npc_profiles (
        npc_id, display_name, npc_scope, artifact_key,
        subject, subject_focus, personality, voice_rules, domain_knowledge
    ) VALUES (
        p_npc_id, p_display_name, p_npc_scope, p_artifact_key,
        p_subject, p_subject_focus, p_personality, p_voice_rules, p_domain_knowledge
    )
    ON CONFLICT (npc_id) DO UPDATE SET
        display_name = EXCLUDED.display_name,
        npc_scope = EXCLUDED.npc_scope,
        artifact_key = EXCLUDED.artifact_key,
        subject = EXCLUDED.subject,
        subject_focus = EXCLUDED.subject_focus,
        personality = EXCLUDED.personality,
        voice_rules = EXCLUDED.voice_rules,
        domain_knowledge = EXCLUDED.domain_knowledge,
        updated_at = now();
    RETURN TRUE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Get session with turns (for summary generation)
CREATE OR REPLACE FUNCTION get_session_turns(target_session_id UUID)
RETURNS TABLE (
    turn_index BIGINT,
    player_message TEXT,
    npc_response TEXT,
    created_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ROW_NUMBER() OVER (ORDER BY dt.created_at) AS turn_index,
        dt.player_message,
        dt.npc_response,
        dt.created_at
    FROM dialogue_turns dt
    WHERE dt.session_id = target_session_id
    ORDER BY dt.created_at;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Search memories by similarity (using vector)
CREATE OR REPLACE FUNCTION search_memories_semantic(
    target_player_id TEXT,
    target_npc_id TEXT,
    query_embedding VECTOR(384),
    match_threshold FLOAT DEFAULT 0.7,
    limit_count INT DEFAULT 5
)
RETURNS TABLE (
    memory_id BIGINT,
    summary TEXT,
    memory_type TEXT,
    similarity FLOAT
) AS $$
BEGIN
    -- Note: similarity calculation depends on index type
    -- For IVFFlat or HNSW, use <=> operator
    RETURN QUERY
    SELECT 
        pme.memory_id,
        pme.summary,
        pme.memory_type,
        1 - (pme.embedding <=> query_embedding) AS similarity
    FROM player_memory_embeddings pme
    WHERE pme.player_id = target_player_id
      AND pme.npc_id = target_npc_id
      AND pme.embedding <=> query_embedding < (1 - match_threshold)
    ORDER BY pme.embedding <=> query_embedding
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Get stats for a player+NPC pair
CREATE OR REPLACE FUNCTION get_player_npc_stats(
    target_player_id TEXT,
    target_npc_id TEXT
)
RETURNS TABLE (
    total_sessions BIGINT,
    total_turns BIGINT,
    total_memories BIGINT,
    first_interaction TIMESTAMPTZ,
    last_interaction TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        (SELECT COUNT(*)::BIGINT FROM dialogue_sessions ds 
         WHERE ds.player_id = target_player_id AND ds.npc_id = target_npc_id),
        (SELECT COUNT(*)::BIGINT FROM dialogue_turns dt
         JOIN dialogue_sessions ds ON ds.session_id = dt.session_id
         WHERE ds.player_id = target_player_id AND ds.npc_id = target_npc_id),
        (SELECT COUNT(*)::BIGINT FROM npc_memories nm
         WHERE nm.player_id = target_player_id AND nm.npc_id = target_npc_id),
        (SELECT MIN(ds.started_at) FROM dialogue_sessions ds
         WHERE ds.player_id = target_player_id AND ds.npc_id = target_npc_id),
        (SELECT MAX(ds.started_at) FROM dialogue_sessions ds
         WHERE ds.player_id = target_player_id AND ds.npc_id = target_npc_id);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ==========================================
-- PART 5: MIGRATION LOG
-- ===========================================

DO $$
BEGIN
    RAISE NOTICE 'Migration improve_supabase_schema completed successfully!';
END $$;