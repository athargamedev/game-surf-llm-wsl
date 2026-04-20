-- Fix pgmq function references in enqueue functions

create or replace function public.enqueue_graph_rebuild()
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    perform pgmq.send('dialogue_graph_queue', jsonb_build_object(
        'job_type', 'rebuild_graph',
        'timestamp', now()
    ));
end;
$$;

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
    perform pgmq.send('memory_embedding_queue', jsonb_build_object(
        'job_type', 'embed_memory',
        'player_id', player_id_param,
        'npc_id', npc_id_param,
        'session_id', session_id_param,
        'timestamp', now()
    ));
end;
$$;
