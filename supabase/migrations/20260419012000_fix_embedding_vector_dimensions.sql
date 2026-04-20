-- Align the GOD memory schema with the 384-dim BGE embedding model.

drop index if exists public.player_memory_embeddings_embedding_idx;
drop index if exists public.dialogue_turn_embeddings_embedding_idx;

alter table public.player_memory_embeddings
    alter column embedding type vector(384)
    using embedding::vector(384);

alter table public.dialogue_turn_embeddings
    alter column embedding type vector(384)
    using embedding::vector(384);

create index if not exists player_memory_embeddings_embedding_idx
    on public.player_memory_embeddings using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);

create index if not exists dialogue_turn_embeddings_embedding_idx
    on public.dialogue_turn_embeddings using ivfflat (embedding vector_cosine_ops)
    with (lists = 100);
