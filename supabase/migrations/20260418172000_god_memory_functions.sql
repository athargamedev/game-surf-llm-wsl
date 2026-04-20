-- GOD Memory RPC Functions

-- Retrieve GOD memory for a player+NPC using vector similarity
create or replace function public.get_god_memory(
    player_id_param text,
    npc_id_param text,
    query_embedding vector default null,
    limit_count integer default 5,
    memory_types text[] default null
)
returns table (
    memory_id bigint,
    memory_type text,
    summary text,
    similarity numeric,
    created_at timestamptz
)
language sql
stable
security definer
set search_path = public
as $$
    select
        m.memory_id,
        m.memory_type,
        m.summary,
        case
            when query_embedding is not null and m.embedding is not null
            then (1 - (m.embedding <=> query_embedding))::numeric
            else 1.0::numeric
        end as similarity,
        m.created_at
    from public.player_memory_embeddings m
    where m.player_id = player_id_param
      and m.npc_id = npc_id_param
      and (memory_types is null or m.memory_type = any(memory_types))
    order by
        case
            when query_embedding is not null and m.embedding is not null
            then m.embedding <=> query_embedding
            else 0
        end,
        m.created_at desc
    limit limit_count;
$$;

-- Insert or update memory embedding (used after memory summarization)
create or replace function public.upsert_memory_embedding(
    player_id_param text,
    npc_id_param text,
    memory_type_param text,
    summary_param text,
    embedding_param vector default null
)
returns bigint
language plpgsql
security definer
set search_path = public
as $$
declare
    memory_id_result bigint;
begin
    insert into public.player_memory_embeddings (
        player_id,
        npc_id,
        memory_type,
        summary,
        embedding
    ) values (
        player_id_param,
        npc_id_param,
        memory_type_param,
        summary_param,
        embedding_param
    )
    on conflict do nothing
    returning memory_id into memory_id_result;
    
    if memory_id_result is null then
        update public.player_memory_embeddings
        set
            summary = summary_param,
            embedding = coalesce(embedding_param, embedding),
            updated_at = now()
        where player_id = player_id_param
          and npc_id = npc_id_param
          and memory_type = memory_type_param
        returning memory_id into memory_id_result;
    end if;
    
    return memory_id_result;
end;
$$;

-- Upgraded relation graph generation with semantic matching
create or replace function public.generate_relation_graph_enhanced(
    use_fuzzy_match boolean default true,
    use_semantic_match boolean default false,
    semantic_threshold numeric default 0.3
)
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
with exact_matches as (
    select
        t.term,
        t.description,
        ds.player_id,
        ds.session_id,
        dt.turn_id,
        case
            when dt.player_message ilike '%' || t.term || '%' then 'player_message'
            else 'npc_response'
        end as source,
        coalesce(nullif(dt.player_message, ''), dt.npc_response) as message,
        'exact' as match_type,
        1.0 as match_score
    from public.dialogue_relation_terms t
    join public.dialogue_turns dt on (
        dt.player_message ilike '%' || t.term || '%'
        or dt.npc_response ilike '%' || t.term || '%'
    )
    join public.dialogue_sessions ds on ds.session_id = dt.session_id
),
fuzzy_matches as (
    select
        t.term,
        t.description,
        ds.player_id,
        ds.session_id,
        dt.turn_id,
        case
            when similarity(dt.player_message, t.term) > 0.3 then 'player_message'
            else 'npc_response'
        end as source,
        coalesce(nullif(dt.player_message, ''), dt.npc_response) as message,
        'fuzzy' as match_type,
        greatest(
            similarity(dt.player_message, t.term),
            similarity(dt.npc_response, t.term)
        ) as match_score
    from public.dialogue_relation_terms t
    join public.dialogue_turns dt on (
        similarity(dt.player_message, t.term) > 0.3
        or similarity(dt.npc_response, t.term) > 0.3
    )
    join public.dialogue_sessions ds on ds.session_id = dt.session_id
    where use_fuzzy_match = true
),
all_matches as (
    select * from exact_matches
    union all
    select * from fuzzy_matches
),
player_term_summary as (
    select
        term,
        description,
        player_id,
        count(*) as matches,
        avg(match_score) as avg_score,
        jsonb_agg(
            jsonb_build_object(
                'session_id', session_id,
                'turn_id', turn_id,
                'source', source,
                'message', message,
                'match_type', match_type,
                'match_score', match_score
            ) order by session_id, turn_id
        ) as messages
    from all_matches
    group by term, description, player_id
),
player_edges as (
    select
        a.term,
        a.player_id as source_player,
        b.player_id as target_player,
        least(a.matches, b.matches) as weight
    from player_term_summary a
    join player_term_summary b using (term)
    where a.player_id < b.player_id
),
graph_nodes as (
    select jsonb_agg(distinct jsonb_build_object(
        'id', 'player:' || player_id,
        'label', player_id,
        'type', 'player'
    )) as player_nodes
    from player_term_summary
),
graph_term_nodes as (
    select jsonb_agg(distinct jsonb_build_object(
        'id', 'term:' || term,
        'label', term,
        'type', 'term',
        'description', description
    )) as term_nodes
    from player_term_summary
),
graph_edges as (
    select jsonb_agg(jsonb_build_object(
        'source', 'player:' || player_id,
        'target', 'term:' || term,
        'type', 'uses',
        'weight', matches,
        'score', avg_score,
        'message_count', jsonb_array_length(messages),
        'messages', messages
    )) as edges
    from player_term_summary
),
shared_player_edges as (
    select jsonb_agg(jsonb_build_object(
        'source', 'player:' || source_player,
        'target', 'player:' || target_player,
        'type', 'shared_term',
        'weight', weight
    )) as edges
    from player_edges
)
select jsonb_build_object(
    'nodes', coalesce((select player_nodes from graph_nodes), '[]'::jsonb) || coalesce((select term_nodes from graph_term_nodes), '[]'::jsonb),
    'edges', coalesce((select edges from graph_edges), '[]'::jsonb) || coalesce((select edges from shared_player_edges), '[]'::jsonb)
);
$$;

-- Enqueue a graph rebuild job
create or replace function public.enqueue_graph_rebuild()
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    perform public.pgmq_send('dialogue_graph_queue', jsonb_build_object(
        'job_type', 'rebuild_graph',
        'timestamp', now()
    ));
end;
$$;

-- Enqueue a memory embedding job
create or replace function public.enqueue_memory_embedding(
    player_id_param text,
    npc_id_param text,
    session_id_param uuid
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    perform public.pgmq_send('memory_embedding_queue', jsonb_build_object(
        'job_type', 'embed_memory',
        'player_id', player_id_param,
        'npc_id', npc_id_param,
        'session_id', session_id_param,
        'timestamp', now()
    ));
end;
$$;
