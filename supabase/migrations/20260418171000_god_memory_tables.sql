-- GOD Memory tables with vector embeddings

create table if not exists public.player_memory_embeddings (
    memory_id bigserial primary key,
    player_id text not null,
    npc_id text not null,
    memory_type text not null default 'session',  -- session, topic, belief, fact
    summary text not null,
    embedding vector(384),  -- BAAI/bge-small-en-v1.5 uses 384 dimensions
    metadata jsonb default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists player_memory_embeddings_player_npc_idx 
    on public.player_memory_embeddings (player_id, npc_id);

create index if not exists player_memory_embeddings_embedding_idx 
    on public.player_memory_embeddings using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);

-- Optional: Store raw turn embeddings for tracing and semantic retrieval
create table if not exists public.dialogue_turn_embeddings (
    turn_id bigint primary key references public.dialogue_turns (turn_id) on delete cascade,
    session_id uuid not null,
    player_id text not null,
    npc_id text not null,
    turn_text text not null,
    embedding vector(384),
    created_at timestamptz not null default now()
);

create index if not exists dialogue_turn_embeddings_session_idx 
    on public.dialogue_turn_embeddings (session_id);

create index if not exists dialogue_turn_embeddings_embedding_idx 
    on public.dialogue_turn_embeddings using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);

-- Materialized relation graph for fast rendering
create table if not exists public.relation_graph_nodes (
    node_id text primary key,
    node_type text not null,  -- player, term, cluster
    label text not null,
    description text,
    metadata jsonb default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create table if not exists public.relation_graph_edges (
    edge_id bigserial primary key,
    source_node_id text not null references public.relation_graph_nodes (node_id) on delete cascade,
    target_node_id text not null references public.relation_graph_nodes (node_id) on delete cascade,
    edge_type text not null,  -- uses, shared_term, semantic_similarity
    weight numeric(10, 4) not null default 1.0,
    metadata jsonb default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists relation_graph_edges_source_idx on public.relation_graph_edges (source_node_id);
create index if not exists relation_graph_edges_target_idx on public.relation_graph_edges (target_node_id);
create index if not exists relation_graph_edges_type_idx on public.relation_graph_edges (edge_type);

-- Queue table for async graph rebuilds (pgmq)
select pgmq.create('dialogue_graph_queue');

-- Queue table for memory embedding jobs
select pgmq.create('memory_embedding_queue');

-- Update timestamps automatically
create or replace function public.update_player_memory_embeddings_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists player_memory_embeddings_update_timestamp on public.player_memory_embeddings;
create trigger player_memory_embeddings_update_timestamp
    before update on public.player_memory_embeddings
    for each row
    execute function public.update_player_memory_embeddings_updated_at();
