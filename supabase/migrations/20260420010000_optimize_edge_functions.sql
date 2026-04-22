-- Optimize edge function RPCs and add efficient dialogue session handling
-- Version: 20260420010000
-- Purpose: Improve NPC dialogue performance with optimized queries

-- ==========================================
-- PART 1: OPTIMIZED SESSION FUNCTIONS
-- ==========================================

-- Keep a cached turn count for Edge functions without duplicating player/NPC
-- ownership on dialogue_turns. The canonical ownership lives on dialogue_sessions.
ALTER TABLE dialogue_sessions
    ADD COLUMN IF NOT EXISTS turn_count INTEGER NOT NULL DEFAULT 0;

-- Fast session retrieval with turn count
CREATE OR REPLACE FUNCTION get_or_create_session(
    p_player_id TEXT,
    p_npc_id TEXT
)
RETURNS TABLE (
    session_id UUID,
    is_new BOOLEAN
) AS $$
DECLARE
    v_session_id UUID;
    v_is_new BOOLEAN := false;
BEGIN
    -- Check for active session (fast index lookup)
    SELECT ds.session_id INTO v_session_id
    FROM dialogue_sessions ds
    WHERE ds.player_id = p_player_id
      AND ds.npc_id = p_npc_id
      AND ds.status = 'active'
    ORDER BY ds.started_at DESC
    LIMIT 1;

    -- If no active session, create one
    IF v_session_id IS NULL THEN
        v_session_id := gen_random_uuid();
        v_is_new := true;

        INSERT INTO dialogue_sessions (
            session_id,
            player_id,
            npc_id,
            status,
            started_at
        ) VALUES (
            v_session_id,
            p_player_id,
            p_npc_id,
            'active',
            now()
        );
    END IF;

    RETURN QUERY SELECT v_session_id, v_is_new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Fast turn insert with session update
CREATE OR REPLACE FUNCTION insert_turn_fast(
    p_session_id UUID,
    p_player_id TEXT,
    p_npc_id TEXT,
    p_player_message TEXT,
    p_npc_response TEXT
)
RETURNS BIGINT AS $$
DECLARE
    v_turn_id BIGINT;
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM dialogue_sessions ds
        WHERE ds.session_id = p_session_id
          AND ds.player_id = p_player_id
          AND ds.npc_id = p_npc_id
    ) THEN
        RAISE EXCEPTION 'Session % does not belong to player % and NPC %',
            p_session_id, p_player_id, p_npc_id;
    END IF;

    -- Insert turn
    INSERT INTO dialogue_turns (
        session_id,
        player_message,
        npc_response
    ) VALUES (
        p_session_id,
        p_player_message,
        p_npc_response
    )
    RETURNING turn_id INTO v_turn_id;

    -- Update cached session turn count for Edge history endpoints.
    UPDATE dialogue_sessions ds
    SET turn_count = (
        SELECT COUNT(*)
        FROM dialogue_turns
        WHERE session_id = p_session_id
    )
    WHERE ds.session_id = p_session_id;

    RETURN v_turn_id;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- End session and trigger memory summary
CREATE OR REPLACE FUNCTION end_session_and_summarize(
    p_session_id UUID
)
RETURNS BOOLEAN AS $$
DECLARE
    v_player_id TEXT;
    v_npc_id TEXT;
BEGIN
    -- Get session info
    SELECT ds.player_id, ds.npc_id
    INTO v_player_id, v_npc_id
    FROM dialogue_sessions ds
    WHERE ds.session_id = p_session_id;

    IF v_player_id IS NULL THEN
        RETURN FALSE;
    END IF;

    -- End the session
    UPDATE dialogue_sessions
    SET status = 'ended',
        ended_at = now()
    WHERE session_id = p_session_id;

    -- The dialogue_sessions trigger summarizes ended sessions.

    RETURN TRUE;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ==========================================
-- PART 2: EFFICIENT MEMORY QUERIES
-- ==========================================

-- Get compact memory for LLM (optimized)
CREATE OR REPLACE FUNCTION get_compact_memory(
    p_player_id TEXT,
    p_npc_id TEXT
)
RETURNS TABLE (
    summary TEXT,
    turn_count BIGINT,
    session_count BIGINT,
    last_interaction TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        nm.summary::TEXT,
        COALESCE(
            (SELECT COUNT(*)::BIGINT
             FROM dialogue_sessions ds
             JOIN dialogue_turns dt ON dt.session_id = ds.session_id
             WHERE ds.player_id = p_player_id AND ds.npc_id = p_npc_id),
            0
        ) AS turn_count,
        (SELECT COUNT(*)::BIGINT
         FROM dialogue_sessions ds
         WHERE ds.player_id = p_player_id AND ds.npc_id = p_npc_id AND ds.status = 'ended') AS session_count,
        (SELECT MAX(ds.started_at)
         FROM dialogue_sessions ds
         WHERE ds.player_id = p_player_id AND ds.npc_id = p_npc_id) AS last_interaction
    FROM npc_memories nm
    WHERE nm.player_id = p_player_id
      AND nm.npc_id = p_npc_id
    ORDER BY nm.created_at DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Get recent turns for a session
CREATE OR REPLACE FUNCTION get_recent_turns(
    p_session_id UUID,
    p_limit INT DEFAULT 20
)
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
    WHERE dt.session_id = p_session_id
    ORDER BY dt.created_at DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ==========================================
-- PART 3: RELATION GRAPH OPTIMIZATIONS
-- ==========================================

-- Rebuild relation graph for a player
CREATE OR REPLACE FUNCTION rebuild_player_graph(
    p_player_id TEXT
)
RETURNS INTEGER AS $$
DECLARE
    v_count INTEGER := 0;
BEGIN
    -- Clear existing player-specific edges first.
    DELETE FROM relation_graph_edges
    WHERE source_node_id = 'player:' || p_player_id
       OR target_node_id = 'player:' || p_player_id;

    -- Clear the player node. Term nodes are shared across players and are kept.
    DELETE FROM relation_graph_nodes
    WHERE node_id = 'player:' || p_player_id;

    INSERT INTO relation_graph_nodes (
        node_id,
        node_type,
        label,
        description,
        metadata
    )
    VALUES (
        'player:' || p_player_id,
        'player',
        p_player_id,
        'Dialogue participant',
        jsonb_build_object('player_id', p_player_id)
    )
    ON CONFLICT (node_id) DO UPDATE SET
        label = EXCLUDED.label,
        description = EXCLUDED.description,
        metadata = EXCLUDED.metadata;

    INSERT INTO relation_graph_nodes (
        node_id,
        node_type,
        label,
        description,
        metadata
    )
    SELECT DISTINCT
        'term:' || lower(regexp_replace(drt.term, '\s+', '_', 'g')),
        'term',
        drt.term,
        drt.description,
        jsonb_build_object('player_id', drt.player_id, 'term', drt.term)
    FROM get_dialogue_relation_matches() drt
    WHERE drt.player_id = p_player_id
    ON CONFLICT (node_id) DO UPDATE SET
        label = EXCLUDED.label,
        description = EXCLUDED.description,
        metadata = relation_graph_nodes.metadata || EXCLUDED.metadata;

    GET DIAGNOSTICS v_count = ROW_COUNT;

    INSERT INTO relation_graph_edges (
        source_node_id,
        target_node_id,
        edge_type,
        weight,
        metadata
    )
    SELECT
        'player:' || p_player_id,
        'term:' || lower(regexp_replace(drt.term, '\s+', '_', 'g')),
        'uses',
        COUNT(*)::numeric,
        jsonb_build_object('player_id', p_player_id, 'term', drt.term)
    FROM get_dialogue_relation_matches() drt
    WHERE drt.player_id = p_player_id
    GROUP BY drt.term
    ON CONFLICT DO NOTHING;

    RETURN v_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ==========================================
-- PART 4: BATCH OPERATIONS
-- ==========================================

-- Batch insert turns efficiently
CREATE OR REPLACE FUNCTION batch_insert_turns(
    p_turns JSONB
)
RETURNS INTEGER AS $$
DECLARE
    v_count INTEGER := 0;
    v_turn JSONB;
BEGIN
    FOR v_turn IN SELECT * FROM jsonb_array_elements(p_turns)
    LOOP
        INSERT INTO dialogue_turns (
            session_id,
            player_message,
            npc_response
        ) VALUES (
            (v_turn->>'session_id')::UUID,
            v_turn->>'player_message',
            v_turn->>'npc_response'
        );

        UPDATE dialogue_sessions ds
        SET turn_count = (
            SELECT COUNT(*)
            FROM dialogue_turns
            WHERE session_id = (v_turn->>'session_id')::UUID
        )
        WHERE ds.session_id = (v_turn->>'session_id')::UUID;

        v_count := v_count + 1;
    END LOOP;

    RETURN v_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ==========================================
-- PART 5: SCHEMA MIGRATION LOG
-- ==========================================

DO $$
BEGIN
    RAISE NOTICE 'Migration optimize_edge_functions completed successfully!';
END $$;
