-- Optimize edge function RPCs and add efficient dialogue session handling
-- Version: 20260420010000
-- Purpose: Improve NPC dialogue performance with optimized queries

-- ==========================================
-- PART 1: OPTIMIZED SESSION FUNCTIONS
-- ==========================================

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
    -- Insert turn
    INSERT INTO dialogue_turns (
        session_id,
        player_id,
        npc_id,
        player_message,
        npc_response
    ) VALUES (
        p_session_id,
        p_player_id,
        p_npc_id,
        p_player_message,
        p_npc_response
    )
    RETURNING id INTO v_turn_id;

    -- Update session turn count (fast)
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

    -- Summarize dialogue
    PERFORM summarize_dialogue_session(
        p_session_id,
        v_player_id,
        v_npc_id
    );

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
    -- Clear existing nodes for player
    DELETE FROM relation_graph_nodes
    WHERE node_id IN (
        SELECT node_id FROM relation_graph_nodes
        WHERE player_id = p_player_id
    );

    -- Clear existing edges
    DELETE FROM relation_graph_edges
    WHERE source_node_id IN (
        SELECT node_id FROM relation_graph_nodes
        WHERE player_id = p_player_id
    );

    -- Insert new nodes from dialogue terms
    INSERT INTO relation_graph_nodes (
        player_id,
        node_type,
        node_label,
        term_text
    )
    SELECT
        p_player_id,
        'term',
        LOWER(drt.term),
        drt.term
    FROM dialogue_relation_terms drt
    WHERE drt.player_id = p_player_id
    ON CONFLICT DO NOTHING;

    -- Count inserted
    GET DIAGNOSTICS v_count = ROW_COUNT;

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
            player_id,
            npc_id,
            player_message,
            npc_response
        ) VALUES (
            (v_turn->>'session_id')::UUID,
            v_turn->>'player_id',
            v_turn->>'npc_id',
            v_turn->>'player_message',
            v_turn->>'npc_response'
        );
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