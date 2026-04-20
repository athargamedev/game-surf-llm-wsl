create table if not exists public.dialogue_relation_terms (
    term_id bigserial primary key,
    term text not null unique,
    description text,
    created_at timestamptz not null default now()
);

create or replace function public.get_dialogue_relation_matches()
returns table (
    term text,
    player_id text,
    npc_id text,
    session_id uuid,
    source text,
    message text,
    matched_at timestamptz
)
language sql
stable
security definer
set search_path = public
as $$
    select
        t.term,
        ds.player_id,
        ds.npc_id,
        dt.session_id,
        case
            when dt.player_message ilike '%' || t.term || '%' then 'player_message'
            else 'npc_response'
        end as source,
        coalesce(
            nullif(dt.player_message, ''),
            dt.npc_response
        ) as message,
        dt.created_at as matched_at
    from public.dialogue_relation_terms t
    join public.dialogue_turns dt on (
        dt.player_message ilike '%' || t.term || '%'
        or dt.npc_response ilike '%' || t.term || '%'
    )
    join public.dialogue_sessions ds on ds.session_id = dt.session_id
    order by t.term, ds.player_id, dt.created_at;
$$;

create or replace function public.generate_dialogue_relation_graph()
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
with term_matches as (
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
        coalesce(
            nullif(dt.player_message, ''),
            dt.npc_response
        ) as message
    from public.dialogue_relation_terms t
    join public.dialogue_turns dt on (
        dt.player_message ilike '%' || t.term || '%'
        or dt.npc_response ilike '%' || t.term || '%'
    )
    join public.dialogue_sessions ds on ds.session_id = dt.session_id
),
player_term_summary as (
    select
        term,
        description,
        player_id,
        count(*) as matches,
        jsonb_agg(
            jsonb_build_object(
                'session_id', session_id,
                'turn_id', turn_id,
                'source', source,
                'message', message
            ) order by session_id, turn_id
        ) as messages
    from term_matches
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
        'term', term,
        'weight', weight
    )) as edges
    from player_edges
)
select jsonb_build_object(
    'nodes', coalesce((select player_nodes from graph_nodes), '[]'::jsonb) || coalesce((select term_nodes from graph_term_nodes), '[]'::jsonb),
    'edges', coalesce((select edges from graph_edges), '[]'::jsonb) || coalesce((select edges from shared_player_edges), '[]'::jsonb)
);
$$;
