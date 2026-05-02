#!/usr/bin/env python3
"""
GOD Memory Worker - processes embedding and graph rebuild jobs from Supabase queues.
Runs embeddings using the local HF embedding model and updates memory/graph tables.
"""

import json
import os
import sys
import time
import signal
from pathlib import Path
from typing import Any, Optional

shutdown_flag = False

def handle_shutdown(signum, frame):
    global shutdown_flag
    print("\n[Worker] Received shutdown signal. Finishing current job...")
    shutdown_flag = True

signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

import requests
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from supabase import Client, create_client
from scripts.supabase_client import SupabaseClient, get_client as get_supabase

ROOT = Path(__file__).resolve().parent.parent


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def get_env_values() -> tuple[str, str, str]:
    env = load_env_file(ROOT / ".env")
    supabase_url = os.environ.get("SUPABASE_URL") or env.get("SUPABASE_URL", "http://127.0.0.1:16433")
    supabase_key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SERVICE_ROLE_KEY")
        or env.get("SUPABASE_SERVICE_ROLE_KEY")
        or env.get("SERVICE_ROLE_KEY")
        or ""
    ).strip()
    embedding_model = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    if not supabase_key:
        print("Error: SUPABASE_SERVICE_ROLE_KEY required")
        sys.exit(1)
    return supabase_url.rstrip("/"), supabase_key, embedding_model


def init_embedding_model(model_name: str):
    """Initialize the HF embedding model."""
    try:
        model = HuggingFaceEmbedding(
            model_name=model_name,
            cache_folder=str(Path.home() / ".cache" / "llama_index"),
            local_files_only=True,
        )
        print(f"✓ Initialized embedding model: {model_name}")
        return model
    except Exception as e:
        print(f"✗ Failed to load embedding model: {e}")
        sys.exit(1)


def create_supabase_client(url: str, key: str) -> Client:
    """Create and test Supabase client."""
    try:
        client = create_client(url, key)
        print(f"✓ Connected to Supabase at {url}")
        return client
    except Exception as e:
        print(f"✗ Failed to connect to Supabase: {e}")
        sys.exit(1)


def parse_payload(payload: Any) -> dict[str, Any]:
    """Normalize pgmq payloads that may arrive as dicts or JSON strings."""
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def load_graph_result(result_data: Any) -> dict[str, Any]:
    """Normalize graph RPC results that may be wrapped in a list."""
    if isinstance(result_data, list):
        if not result_data:
            return {}
        first_item = result_data[0]
        return first_item if isinstance(first_item, dict) else {}
    if isinstance(result_data, dict):
        return result_data
    return {}


def clear_relation_graph(supabase: Client) -> None:
    """Remove the materialized graph so a rebuild can replace it cleanly."""
    supabase.table("relation_graph_edges").delete().neq("edge_id", -1).execute()
    supabase.table("relation_graph_nodes").delete().neq("node_id", "__never__").execute()


def persist_relation_graph(supabase: Client, graph_data: dict[str, Any]) -> None:
    """Persist the generated relation graph into the materialized tables."""
    nodes = graph_data.get("nodes") or []
    edges = graph_data.get("edges") or []

    clear_relation_graph(supabase)

    node_rows: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = node.get("node_id") or node.get("id")
        label = node.get("label") or node_id
        node_type = node.get("node_type") or node.get("type") or "unknown"
        if not node_id:
            continue
        node_rows.append(
            {
                "node_id": node_id,
                "node_type": node_type,
                "label": label,
                "description": node.get("description"),
                "metadata": {
                    key: value
                    for key, value in node.items()
                    if key not in {"node_id", "id", "node_type", "type", "label", "description"}
                },
            }
        )

    if node_rows:
        supabase.table("relation_graph_nodes").insert(node_rows).execute()

    edge_rows: list[dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        source_id = edge.get("source_node_id") or edge.get("source")
        target_id = edge.get("target_node_id") or edge.get("target")
        edge_type = edge.get("edge_type") or edge.get("type") or "related"
        if not source_id or not target_id:
            continue
        edge_rows.append(
            {
                "source_node_id": source_id,
                "target_node_id": target_id,
                "edge_type": edge_type,
                "weight": edge.get("weight", 1.0),
                "metadata": {
                    key: value
                    for key, value in edge.items()
                    if key not in {"source_node_id", "target_node_id", "source", "target", "edge_type", "type", "weight"}
                },
            }
        )

    if edge_rows:
        supabase.table("relation_graph_edges").insert(edge_rows).execute()


def process_memory_embedding_job(
    supabase: Client,
    embedding_model,
    player_id: str,
    npc_id: str,
    session_id: str,
) -> bool:
    """Process a memory embedding job: fetch session memory and embed it."""
    try:
        session_resp = (
            supabase.table("dialogue_sessions")
            .select("*")
            .eq("session_id", session_id)
            .limit(1)
            .execute()
        )
        if not session_resp.data:
            print(f"  Session {session_id} not found")
            return False

        # Prefer the exact memory row created for this session; fall back to the most recent one.
        memory_resp = (
            supabase.table("npc_memories")
            .select("summary, raw_json")
            .match({"player_id": player_id, "npc_id": npc_id})
            .order("created_at", desc=True)
            .limit(25)
            .execute()
        )
        if not memory_resp.data:
            print(f"  No memory found for {player_id}/{npc_id}")
            return False

        summary = None
        for row in memory_resp.data:
            raw_json = row.get("raw_json") or {}
            if raw_json.get("session_id") == session_id:
                summary = row.get("summary")
                break
        if summary is None:
            summary = memory_resp.data[0].get("summary")
        if not summary:
            print(f"  No summary available for {player_id}/{npc_id} session {session_id}")
            return False

        try:
            embedding_vector = embedding_model.get_text_embedding(summary)
        except Exception as e:
            print(f"  Embedding generation failed: {e}")
            return False

        supabase.rpc(
            "upsert_memory_embedding",
            {
                "player_id_param": player_id,
                "npc_id_param": npc_id,
                "memory_type_param": "session",
                "summary_param": summary,
                "embedding_param": embedding_vector,
            },
        ).execute()

        print(f"  ✓ Embedded memory for {player_id}/{npc_id}")
        return True
    except Exception as e:
        print(f"  Error processing memory embedding: {e}")
        return False


def process_graph_rebuild_job(
    supabase: Client,
    use_fuzzy_match: bool = True,
    use_semantic_match: bool = False,
) -> bool:
    """Process a graph rebuild job: regenerate relation graph."""
    try:
        result = supabase.rpc(
            "generate_relation_graph_enhanced",
            {
                "use_fuzzy_match": use_fuzzy_match,
                "use_semantic_match": use_semantic_match,
            },
        ).execute()

        graph_data = load_graph_result(result.data)
        if not graph_data:
            print("  Graph rebuild returned no data; clearing materialized graph")
            clear_relation_graph(supabase)
            return True

        persist_relation_graph(supabase, graph_data)
        print("  ✓ Graph rebuilt and persisted successfully")
        return True
    except Exception as e:
        print(f"  Error processing graph rebuild: {e}")
        return False


def poll_queues(supabase: Client, embedding_model, poll_interval: int = 5, batch_size: int = 10) -> None:
    """Poll and process job queues."""
    print(f"\n[Worker] Starting job queue polling (interval={poll_interval}s)...\n")

    while not shutdown_flag:
        try:
            # Process graph rebuild jobs
            try:
                graph_jobs = supabase.rpc("pgmq_read", {
                    "queue_name": "dialogue_graph_queue",
                    "limit_count": batch_size,
                    "vt": 30,  # visibility timeout
                }).execute()
                
                if graph_jobs.data:
                    for job in graph_jobs.data:
                        payload = parse_payload(job.get("msg"))
                        print(f"[Graph] Processing job {job.get('msg_id')}: {payload}")
                        if process_graph_rebuild_job(
                            supabase,
                            use_fuzzy_match=bool(payload.get("use_fuzzy_match", True)),
                            use_semantic_match=bool(payload.get("use_semantic_match", False)),
                        ):
                            supabase.rpc("pgmq_pop", {
                                "queue_name": "dialogue_graph_queue",
                                "msg_id": job.get("msg_id"),
                            }).execute()
            except Exception as e:
                # pgmq_read might not exist, skip silently
                pass

            # Process memory embedding jobs
            try:
                embed_jobs = supabase.rpc("pgmq_read", {
                    "queue_name": "memory_embedding_queue",
                    "limit_count": batch_size,
                    "vt": 30,
                }).execute()
                
                if embed_jobs.data:
                    for job in embed_jobs.data:
                        msg = parse_payload(job.get("msg"))
                        print(f"[Embed] Processing job {job.get('msg_id')}: {msg.get('player_id')}/{msg.get('npc_id')}")
                        if process_memory_embedding_job(
                            supabase,
                            embedding_model,
                            msg.get("player_id"),
                            msg.get("npc_id"),
                            msg.get("session_id"),
                        ):
                            supabase.rpc("pgmq_pop", {
                                "queue_name": "memory_embedding_queue",
                                "msg_id": job.get("msg_id"),
                            }).execute()
            except Exception as e:
                # pgmq_read might not exist, skip silently
                pass

            time.sleep(poll_interval)

        except KeyboardInterrupt:
            print("\n[Worker] Shutting down...")
            break
        except Exception as e:
            print(f"[Worker] Error in polling loop: {e}")
            time.sleep(poll_interval)


def main() -> None:
    supabase_url, supabase_key, embedding_model_name = get_env_values()
    
    print("=" * 70)
    print("GOD Memory Worker - Supabase Queue Processor")
    print("=" * 70)
    
    embedding_model = init_embedding_model(embedding_model_name)
    supabase = create_supabase_client(supabase_url, supabase_key)
    supabase_wrapper = get_supabase()
    
    poll_queues(supabase, embedding_model)


if __name__ == "__main__":
    main()
