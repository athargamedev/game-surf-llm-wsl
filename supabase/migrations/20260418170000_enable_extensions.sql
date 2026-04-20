-- Enable essential extensions for GOD memory and relation graphs
create extension if not exists vector;
create extension if not exists pgmq;
create extension if not exists fuzzystrmatch;
create extension if not exists pg_trgm;
create extension if not exists tablefunc;

-- Create index_advisor if available (optional, may not exist in all versions)
-- create extension if not exists index_advisor;

-- Enable trigram index for fuzzy matching on dialogue text
create index if not exists dialogue_turns_player_message_trgm_idx on public.dialogue_turns using gist (player_message gist_trgm_ops);
create index if not exists dialogue_turns_npc_response_trgm_idx on public.dialogue_turns using gist (npc_response gist_trgm_ops);

-- Enable trigram index on terms for fuzzy search
create index if not exists dialogue_relation_terms_term_trgm_idx on public.dialogue_relation_terms using gist (term gist_trgm_ops);
