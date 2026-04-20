create table if not exists public.player_profiles (
    player_id text primary key,
    display_name text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- Disable RLS for player_profiles table since it's managed by the service
alter table public.player_profiles disable row level security;

create or replace function public.update_player_profiles_updated_at()
returns trigger language plpgsql as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists player_profiles_update_timestamp on public.player_profiles;
create trigger player_profiles_update_timestamp
    before update on public.player_profiles
    for each row
    execute function public.update_player_profiles_updated_at();
