-- Public wrappers for pgmq queue operations used by the worker.

create or replace function public.pgmq_read(
    queue_name text,
    limit_count integer,
    vt integer
)
returns table (
    msg_id bigint,
    msg jsonb
)
language sql
volatile
security definer
set search_path = public, pgmq
as $$
    select
        r.msg_id,
        r.message as msg
    from pgmq.read(queue_name, limit_count, vt, '{}'::jsonb) as r;
$$;

create or replace function public.pgmq_pop(
    queue_name text,
    msg_id bigint
)
returns void
language sql
volatile
security definer
set search_path = public, pgmq
as $$
    select pgmq.delete(queue_name, msg_id);
$$;
