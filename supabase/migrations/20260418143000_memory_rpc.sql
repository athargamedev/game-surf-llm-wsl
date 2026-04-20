create or replace function public.summarize_dialogue_session(
    session_id_param uuid,
    player_id_param text,
    npc_id_param text
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
    turn_count integer;
    summary_text text;
begin
    select count(*)
    into turn_count
    from public.dialogue_turns
    where session_id = session_id_param;

    if turn_count = 0 then
        summary_text := 'No dialogue turns were recorded for this session.';
    else
        select string_agg(
            'Player: ' || left(player_message, 240) || E'\nNPC: ' || left(npc_response, 240),
            E'\n'
            order by created_at
        )
        into summary_text
        from public.dialogue_turns
        where session_id = session_id_param;
    end if;

    insert into public.npc_memories (
        player_id,
        npc_id,
        summary,
        raw_json
    )
    values (
        player_id_param,
        npc_id_param,
        left(summary_text, 2000),
        jsonb_build_object(
            'session_id', session_id_param,
            'session_turn_count', turn_count,
            'summarizer', 'postgres_compact_v1'
        )
    );
end;
$$;

drop function if exists public.get_player_npc_memory(text, text);

create function public.get_player_npc_memory(
    player_id_param text,
    npc_id_param text
)
returns table (
    player_id text,
    npc_id text,
    summary text,
    session_count bigint,
    updated_at timestamptz
)
language sql
stable
security definer
set search_path = public
as $$
    select
        m.player_id,
        m.npc_id,
        m.summary,
        count(*) over (partition by m.player_id, m.npc_id) as session_count,
        m.created_at as updated_at
    from public.npc_memories m
    where m.player_id = player_id_param
      and m.npc_id = npc_id_param
    order by m.created_at desc
    limit 1;
$$;

create or replace function public.summarize_ended_dialogue_session()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    if new.status = 'ended'
       and (old.status is distinct from new.status or old.ended_at is distinct from new.ended_at) then
        perform public.summarize_dialogue_session(new.session_id, new.player_id, new.npc_id);
    end if;

    return new;
end;
$$;

drop trigger if exists on_session_end on public.dialogue_sessions;
drop trigger if exists trg_summarize_ended_dialogue_session on public.dialogue_sessions;

create trigger trg_summarize_ended_dialogue_session
after update on public.dialogue_sessions
for each row
execute function public.summarize_ended_dialogue_session();
