-- Fix GOD memory queue payloads and make memory upserts truly idempotent.

create or replace function public.enqueue_graph_rebuild(
    use_fuzzy_match boolean default true,
    use_semantic_match boolean default false
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
    perform pgmq.send('dialogue_graph_queue', jsonb_build_object(
        'job_type', 'rebuild_graph',
        'use_fuzzy_match', use_fuzzy_match,
        'use_semantic_match', use_semantic_match,
        'timestamp', now()
    ));
end;
$$;

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
    update public.player_memory_embeddings
    set
        summary = summary_param,
        embedding = coalesce(embedding_param, embedding),
        updated_at = now()
    where player_id = player_id_param
      and npc_id = npc_id_param
      and memory_type = memory_type_param
    returning memory_id into memory_id_result;

    if memory_id_result is null then
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
        returning memory_id into memory_id_result;
    end if;

    return memory_id_result;
end;
$$;
