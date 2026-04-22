#!/usr/bin/env python
"""Integrated Game_Surf LLM server with relay, Supabase memory, and reload endpoints."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import asyncio
import gc
import json
import os
import re
import uuid
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from llama_index.core import StorageContext, SimpleDirectoryReader, Settings, VectorStoreIndex, load_index_from_storage
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.llama_cpp import LlamaCPP
from llama_index.core.memory import ChatMemoryBuffer
from supabase import Client, create_client
from scripts.supabase_client import SupabaseClient, get_client as get_supabase
import requests
from typing import Optional

BASE_URL = os.environ.get("LLM_SERVER_URL", "http://127.0.0.1:8000")

TOOLS_LLM_ROOT = Path(__file__).resolve().parents[1]
NPC_MODEL_MANIFEST_GLOB = "exports/**/npc_model_manifest.json"


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE pairs without overriding the active shell."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


load_env_file(TOOLS_LLM_ROOT / ".env")

MODEL_PATH = os.environ.get(
    "MODEL_PATH",
    "exports/training_test_export/gguf_gguf/llama-3.2-3b-instruct.Q4_K_M.gguf",
)
BASE_MODEL_PATH = MODEL_PATH
LORE_DIR = os.environ.get("LORE_DIR", "research/world_lore")
INDEX_STORAGE = os.environ.get("INDEX_STORAGE", "datasets/indexes/world_lore")
SUPABASE_URL = os.environ.get("SUPABASE_URL", "http://127.0.0.1:16433")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SERVICE_ROLE_KEY")
    or ""
).strip()
ENABLE_SUPABASE = os.environ.get("ENABLE_SUPABASE", "true").lower() == "true"
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
CHAT_HISTORY_TOKEN_LIMIT = int(os.environ.get("CHAT_HISTORY_TOKEN_LIMIT", "1500"))
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.35"))
LLM_MAX_NEW_TOKENS = int(os.environ.get("LLM_MAX_NEW_TOKENS", "96"))
LLAMA_N_GPU_LAYERS = int(os.environ.get("LLAMA_N_GPU_LAYERS", "32"))  # Llama-3.2-3B has 28 layers; 32 = "all on GPU"
DIRECT_CHAT_MAX_TURNS = int(os.environ.get("DIRECT_CHAT_MAX_TURNS", "6"))
GRAPH_REFRESH_INTERVAL_SECONDS = int(os.environ.get("GRAPH_REFRESH_INTERVAL_SECONDS", "1800"))
PRELOAD_NPC_MODELS = os.environ.get("PRELOAD_NPC_MODELS", "false").lower() == "true"
ENABLE_NPC_LORA = os.environ.get("ENABLE_NPC_LORA", "true").lower() == "true"
TEST_MESSAGE_DELAY_SECONDS = float(os.environ.get("TEST_MESSAGE_DELAY_SECONDS", "5"))
TEST_IDENTITY_PROBE_DELAY_SECONDS = float(os.environ.get("TEST_IDENTITY_PROBE_DELAY_SECONDS", "4"))
TEST_MEMORY_PROCESSING_DELAY_SECONDS = float(os.environ.get("TEST_MEMORY_PROCESSING_DELAY_SECONDS", "25"))
TEST_PLAYER_DELAY_SECONDS = float(os.environ.get("TEST_PLAYER_DELAY_SECONDS", "4"))
TEST_NPC_SWITCH_DELAY_SECONDS = float(os.environ.get("TEST_NPC_SWITCH_DELAY_SECONDS", "8"))
TEST_PHASE_MEMORY_DELAY_SECONDS = float(os.environ.get("TEST_PHASE_MEMORY_DELAY_SECONDS", "35"))
MEMORY_SLOT = "[MEMORY_CONTEXT: {player_memory_summary}]"

supabase_client: Client | None = None
supabase_wrapper: SupabaseClient | None = None
chat_engines: dict[str, object] = {}
# active_sessions: maps (player_id, npc_id) -> session_id
active_sessions: dict[str, str] = {}
llm_loaded = False
index_loaded = False
llm_load_error: str | None = None
index_load_error: str | None = None
npc_model_registry: dict[str, dict] = {}
active_npc_id: str | None = None
active_lora_adapter_path: str | None = None
graph_refresh_thread_started = False
llm_generation_lock = threading.Lock()

request_stats = {"total": 0, "errors": 0, "total_response_time_ms": 0}
request_timestamps: list[float] = []

STOP_STRINGS = [
    "<|eot_id|>",
    "<|start_header_id|>user<|end_header_id|>",
    "<|start_header_id|>assistant<|end_header_id|>",
    "\nuser:",
    "\nassistant:",
    "\nassistant\nuser:",
]

RESPONSE_CUTOFF_PATTERNS = [
    r"<\|eot_id\|>",
    r"<\|start_header_id\|>user<\|end_header_id\|>",
    r"<\|start_header_id\|>assistant<\|end_header_id\|>",
    r"\nassistant\s*\nuser:",
    r"\nuser:",
    r"\nassistant:",
    r"\bassistant\s*\nuser:",
]


@dataclass
class DirectNpcChatSession:
    system_prompt: str
    history: list[ChatMessage] = field(default_factory=list)


# ── Request / Response models ─────────────────────────────────────────────────

class ChatRequest(BaseModel):
    npc_id: str
    player_id: str
    message: str
    session_id: str | None = None  # optional — relay creates one if absent


class ChatResponse(BaseModel):
    npc_response: str
    session_id: str | None = None


class StartSessionRequest(BaseModel):
    player_id: str
    npc_id: str
    player_name: str | None = None


class StartSessionResponse(BaseModel):
    session_id: str
    player_id: str
    npc_id: str
    memory_summary: str | None = None


class EndSessionRequest(BaseModel):
    session_id: str
    player_id: str
    npc_id: str


class SessionHistoryResponse(BaseModel):
    session_id: str
    player_id: str
    npc_id: str
    turns: list[dict]


class HealthResponse(BaseModel):
    status: str


class StatusResponse(BaseModel):
    model_path: str
    base_model_path: str
    active_npc_id: str | None = None
    active_lora_adapter_path: str | None = None
    model_loaded: bool
    index_path: str
    index_loaded: bool
    npc_model_registry_size: int
    supabase_enabled: bool
    supabase_connected: bool
    llm_error: str | None = None
    index_error: str | None = None
    gpu_acceleration: dict | None = None


class GodMemoryRequest(BaseModel):
    player_id: str
    npc_id: str
    limit: int = 5
    memory_types: list[str] | None = None
    include_profile: bool = True
    include_recent_npc_memories: bool = True
    include_related_terms: bool = True


class GodMemoryResponse(BaseModel):
    player_id: str
    npc_id: str
    profile: dict | None = None
    memories: list[dict]
    recent_npc_memories: list[dict] = []
    related_terms: list[dict] = []


class GraphRebuildRequest(BaseModel):
    use_fuzzy_match: bool = True
    use_semantic_match: bool = False


class GraphRebuildResponse(BaseModel):
    status: str
    message: str


def create_supabase_client() -> None:
    global supabase_client
    if not ENABLE_SUPABASE:
        return
    if not SUPABASE_KEY:
        print("Supabase skipped: SUPABASE_SERVICE_ROLE_KEY is empty (set in .env or environment).")
        return

    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        print(f"Connected to Supabase at {SUPABASE_URL}")
    except Exception as exc:
        supabase_client = None
        print(f"Supabase connection failed: {exc}")


def load_npc_model_registry() -> None:
    global npc_model_registry
    registry: dict[str, dict] = {}

    manifest_paths = sorted(
        TOOLS_LLM_ROOT.glob(NPC_MODEL_MANIFEST_GLOB),
        key=lambda path: (
            0 if "exports/npc_models/" not in path.as_posix() else 1,
            path.as_posix(),
        ),
    )

    for manifest_path in manifest_paths:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"Skipping invalid NPC manifest {manifest_path}: {exc}")
            continue

        manifest["_manifest_path"] = str(manifest_path)
        keys = {
            manifest.get("npc_key"),
            manifest.get("artifact_key"),
            manifest.get("supabase_npc_id"),
        }
        for key in keys:
            if key:
                registry[key] = manifest

    npc_model_registry = registry


def normalize_manifest_path(path_str: str | None) -> str | None:
    if not path_str:
        return None

    candidate = Path(path_str)
    if not candidate.is_absolute():
        rooted = TOOLS_LLM_ROOT / candidate
        if rooted.exists():
            return str(rooted)
    if candidate.exists():
        return str(candidate)

    normalized = path_str.replace("\\", "/")

    for marker in ["Tools/LLM/", "Tools/LLM"]:
        if marker in normalized:
            suffix = normalized.split(marker, 1)[1].lstrip("/")
            remapped = TOOLS_LLM_ROOT / suffix
            if remapped.exists():
                return str(remapped)

    exports_marker = "exports/"
    if exports_marker in normalized:
        suffix = normalized.split(exports_marker, 1)[1]
        remapped = TOOLS_LLM_ROOT / "exports" / suffix
        if remapped.exists():
            return str(remapped)

    return path_str


def resolve_lora_adapter_path_for_npc(npc_id: str) -> str | None:
    manifest = npc_model_registry.get(npc_id)
    if not manifest:
        return None

    adapter_dir = normalize_manifest_path(manifest.get("artifacts", {}).get("adapter_dir"))
    if adapter_dir:
        gguf_adapter_file = Path(adapter_dir) / "adapter_model.gguf"
        if gguf_adapter_file.exists():
            return str(gguf_adapter_file)
        adapter_file = Path(adapter_dir) / "adapter_model.safetensors"
        if adapter_file.exists():
            print(
                f"Found PEFT adapter for {npc_id}, but llama.cpp runtime requires "
                f"a converted adapter_model.gguf: {adapter_file}"
            )

    runtime_lora = normalize_manifest_path(manifest.get("runtime", {}).get("lora_adapter_path"))
    if runtime_lora and Path(runtime_lora).exists() and Path(runtime_lora).suffix == ".gguf":
        return runtime_lora

    return None


def _log_lora_resolution_status(npc_id: str, adapter_path: str | None, model_path: str) -> None:
    """Log clear diagnostic info about LoRA resolution."""
    if adapter_path:
        size_mb = round(Path(adapter_path).stat().st_size / 1024 / 1024, 2) if Path(adapter_path).exists() else 0
        print(f"[LoRA] {npc_id}: adapter loaded ({size_mb} MB), model={model_path}")
    else:
        print(f"[LoRA] {npc_id}: NO LoRA adapter found — using base model ({model_path})")
        manifest = npc_model_registry.get(npc_id)
        if manifest:
            manifest_adapter_dir = manifest.get("artifacts", {}).get("adapter_dir")
            manifest_runtime_lora = manifest.get("runtime", {}).get("lora_adapter_path")
            print(f"[LoRA]   manifest adapter_dir: {manifest_adapter_dir}")
            print(f"[LoRA]   manifest runtime.lora_adapter_path: {manifest_runtime_lora}")


def resolve_gguf_model_path_for_npc(npc_id: str) -> str | None:
    manifest = npc_model_registry.get(npc_id)
    if not manifest:
        return None

    artifact_path = normalize_manifest_path(manifest.get("artifacts", {}).get("gguf_path"))
    if artifact_path and Path(artifact_path).is_file():
        return artifact_path

    relay_path = normalize_manifest_path(manifest.get("runtime", {}).get("relay_model_path"))
    if relay_path and Path(relay_path).is_file():
        return relay_path

    return None


def npc_runtime_snapshot(manifest: dict) -> dict:
    npc_id = manifest.get("npc_key") or manifest.get("supabase_npc_id") or manifest.get("artifact_key")
    adapter_path = resolve_lora_adapter_path_for_npc(str(npc_id)) if npc_id else None
    gguf_path = resolve_gguf_model_path_for_npc(str(npc_id)) if npc_id else None
    return {
        "npc_key": manifest.get("npc_key"),
        "artifact_key": manifest.get("artifact_key"),
        "supabase_npc_id": manifest.get("supabase_npc_id"),
        "display_name": manifest.get("profile", {}).get("display_name"),
        "subject": manifest.get("profile", {}).get("subject"),
        "adapter_path": adapter_path,
        "gguf_path": gguf_path,
        "runtime_mode": "lora_adapter" if adapter_path else ("dedicated_gguf" if gguf_path else "base_model"),
    }


def npc_adapter_is_active(npc_id: str) -> bool:
    resolved = resolve_lora_adapter_path_for_npc(npc_id)
    if not resolved or not active_lora_adapter_path:
        return False
    return Path(resolved).resolve() == Path(active_lora_adapter_path).resolve()


def llama3_messages_to_prompt(messages: list[ChatMessage]) -> str:
    prompt_parts = []
    for message in messages:
        role = message.role.value if hasattr(message.role, "value") else str(message.role)
        content = str(message.content).strip()
        prompt_parts.append(
            f"<|start_header_id|>{role}<|end_header_id|>\n\n{content}<|eot_id|>"
        )
    return "<|begin_of_text|>" + "".join(prompt_parts) + "<|start_header_id|>assistant<|end_header_id|>\n\n"


def llama3_completion_to_prompt(completion: str) -> str:
    completion = completion.strip()
    return (
        "<|begin_of_text|>"
        "<|start_header_id|>user<|end_header_id|>\n\n"
        f"{completion}<|eot_id|>"
        "<|start_header_id|>assistant<|end_header_id|>\n\n"
    )


def clean_npc_response(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"(?is)^.*?<\|start_header_id\|>assistant<\|end_header_id\|>\s*", "", cleaned)
    for pattern in RESPONSE_CUTOFF_PATTERNS:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            cleaned = cleaned[: match.start()].strip()
            break

    cleaned = re.sub(r"(?is)<\|.*?$", "", cleaned)
    cleaned = re.sub(r"(?is)\b(system|user|assistant)\s*[:\-].*$", "", cleaned)
    cleaned = re.sub(r"(?is)\bsystem\s+prompt\s*[:\-].*$", "", cleaned)
    cleaned = re.sub(r"(?is)^you are .*?\[MEMORY_CONTEXT.*$", "", cleaned)
    cleaned = re.sub(r"(?is)\[MEMORY_CONTEXT\].*$", "", cleaned)
    cleaned = re.sub(r"^\s*assistant\s*[:\-]?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+\Z", "", cleaned)
    cleaned = cleaned.strip()
    if not cleaned or len(cleaned.split()) < 3:
        return "I need a moment to gather that thought. Please ask me again."
    return cleaned


def extract_chat_text(response) -> str:
    message = getattr(response, "message", None)
    content = getattr(message, "content", None)
    if content:
        return str(content)
    return str(response)


def build_system_prompt(npc_id: str) -> str:
    """Build the system prompt for an NPC.

    Key design decisions:
    - Display name is the ONLY identity marker (no "You focus on X" — model invents new names)
    - Tone/style as adjectives, not descriptors that sound like part of the name
    - Concise so the model stops after the name and doesn't elaborate
    - Short: model generates less, fewer opportunities for hallucination
    """
    try:
        profiles_path = TOOLS_LLM_ROOT / "datasets" / "configs" / "npc_profiles.json"
        if not profiles_path.exists():
            return f"You are a helpful NPC inside Game_Surf. {MEMORY_SLOT}"

        profiles_data = json.loads(profiles_path.read_text(encoding="utf-8"))
        profiles = profiles_data.get("profiles", {})
        prof = profiles.get(npc_id)
        if not prof:
            for key, value in profiles.items():
                if npc_id in key or key in npc_id:
                    prof = value
                    break

        if prof:
            display_name = prof.get("display_name", npc_id)
            voice_rules = prof.get("voice_rules", [])[:4]
            voice_rules_text = " ".join(f"- {rule}" for rule in voice_rules)

            # Strip "professor", "doctor", "dr." from display name to avoid "I am Professor Professor"
            clean_name = re.sub(r"^(Professor|Dr\.|Doctor|The)\s+", "", display_name, flags=re.IGNORECASE).strip()

            # No "You focus on X" — that phrase makes the model say "I'm X Analyst" or "I specialize in X"
            system_prompt = (
                f"You are {clean_name}. {MEMORY_SLOT} "
                f"{voice_rules_text} "
                "Answer directly in 1-3 sentences. Stay in character. "
                "Do not introduce yourself, do not describe your role, do not add titles or labels."
            )
        else:
            system_prompt = f"You are {npc_id}, an NPC inside Game_Surf. {MEMORY_SLOT}"
    except Exception as exc:
        print(f"Warn: failed to build system prompt for {npc_id}: {exc}")
        system_prompt = f"You are a helpful NPC inside Game_Surf. {MEMORY_SLOT}"
    return system_prompt


def extract_keywords(text: str) -> set[str]:
    if not text:
        return set()
    words = text.lower().split()
    return {w.strip(".,!?;:()[]{}") for w in words if len(w) > 3}


def score_memory_relevance(memory_text: str, current_message: str) -> float:
    memory_kw = extract_keywords(memory_text)
    current_kw = extract_keywords(current_message)
    if not current_kw:
        return 0.0
    return len(memory_kw & current_kw) / len(current_kw)


def load_player_context(player_id: str, npc_id: str, current_message: str = "") -> str:
    print(f"[MEMORY] load_player_context called for player_id={player_id} npc_id={npc_id}")
    profile_lines: list[str] = []
    memory_lines: list[str] = []
    term_lines: list[str] = []
    if supabase_client is None:
        print(f"[MEMORY] Supabase client is not connected")
        return "No saved player memory."

    try:
        profile_response = (
            supabase_client.table("player_profiles")
            .select("display_name")
            .eq("player_id", player_id)
            .limit(1)
            .execute()
        )
        if profile_response.data:
            profile = profile_response.data[0]
            display_name = (profile.get("display_name") or "").strip()
            if display_name:
                profile_lines.append(f"Display name: {display_name}")
    except Exception as exc:
        print(f"Player profile retrieval skipped: {exc}")

    try:
        session_count_resp = (
            supabase_client.table("dialogue_sessions")
            .select("session_id", count="exact")
            .match({"player_id": player_id, "npc_id": npc_id})
            .execute()
        )
        session_count = session_count_resp.count or 0
        
        mem_limit = min(5, max(2, session_count)) if session_count > 10 else 5
        print(f"[MEMORY] Querying npc_memories for player_id={player_id} npc_id={npc_id} limit={mem_limit}")
        mem_response = (
            supabase_client.table("npc_memories")
            .select("summary, created_at, raw_json")
            .match({"player_id": player_id, "npc_id": npc_id})
            .order("created_at", desc=True)
            .limit(mem_limit)
            .execute()
        )
        print(f"[MEMORY] npc_memories rows returned: {len(mem_response.data) if mem_response.data else 0}")
        if mem_response.data:
            summaries: list[str] = []
            for row in mem_response.data:
                summary = (row.get("summary") or "").strip()
                if summary:
                    raw = row.get("raw_json") or {}
                    turn_count = raw.get("session_turn_count", "?")
                    summaries.append(f"[{turn_count}t] {summary[:250].replace(chr(10), ' ')}")
            if summaries:
                if session_count > 0:
                    memory_lines.append(f"Total conversations: {session_count}")
                for idx, summary in enumerate(summaries, start=1):
                    memory_lines.append(f"{idx}. {summary}")
    except Exception as exc:
        print(f"NPC memory retrieval skipped: {exc}")

    try:
        player_node_id = f"player:{player_id}"
        edge_response = (
            supabase_client.table("relation_graph_edges")
            .select("source_node_id, target_node_id, edge_type, weight, metadata, created_at")
            .eq("source_node_id", player_node_id)
            .eq("edge_type", "uses")
            .order("weight", desc=True)
            .limit(5)
            .execute()
        )
        edges = edge_response.data or []
        if edges:
            target_ids = [edge.get("target_node_id") for edge in edges if edge.get("target_node_id")]
            node_lookup: dict[str, dict] = {}
            if target_ids:
                node_response = (
                    supabase_client.table("relation_graph_nodes")
                    .select("node_id, node_type, label, description")
                    .in_("node_id", target_ids)
                    .execute()
                )
                for node in node_response.data or []:
                    node_lookup[node["node_id"]] = node

            term_parts: list[str] = []
            for edge in edges:
                target_id = edge.get("target_node_id")
                if not target_id:
                    continue
                node = node_lookup.get(target_id, {})
                label = node.get("label") or target_id.removeprefix("term:")
                description = node.get("description") or ""
                term_parts.append(f"{label} ({description})".strip())

            if term_parts:
                for idx, term_text in enumerate(term_parts, start=1):
                    term_lines.append(f"{idx}. {term_text}")
    except Exception as exc:
        print(f"Graph relation retrieval skipped: {exc}")

    sections: list[str] = []
    if profile_lines:
        sections.append("Player Profile:\n" + "\n".join(profile_lines))
    if memory_lines:
        sections.append("Recent NPC Memories:\n" + "\n".join(memory_lines))
    if term_lines:
        sections.append("Related Terms:\n" + "\n".join(term_lines))

    return "\n\n".join(sections) if sections else "No saved player memory."


def apply_memory_slot(system_prompt: str, player_id: str, npc_id: str) -> str:
    player_memory_summary = load_player_context(player_id, npc_id)
    if MEMORY_SLOT in system_prompt:
        return system_prompt.replace(MEMORY_SLOT, f"[MEMORY_CONTEXT]\n{player_memory_summary}")
    return f"{system_prompt}\n[MEMORY_CONTEXT]\n{player_memory_summary}"


def enqueue_memory_embedding_job(player_id: str, npc_id: str, session_id: str) -> None:
    if supabase_client is None:
        raise RuntimeError("Supabase not connected")

    supabase_client.rpc(
        "enqueue_memory_embedding",
        {
            "player_id_param": player_id,
            "npc_id_param": npc_id,
            "session_id_param": session_id,
        },
    ).execute()


def enqueue_graph_rebuild_job(
    use_fuzzy_match: bool = True,
    use_semantic_match: bool = False,
) -> None:
    if supabase_client is None:
        raise RuntimeError("Supabase not connected")

    supabase_client.rpc(
        "enqueue_graph_rebuild",
        {
            "use_fuzzy_match": use_fuzzy_match,
            "use_semantic_match": use_semantic_match,
        },
    ).execute()


def graph_refresh_loop() -> None:
    while True:
        time.sleep(GRAPH_REFRESH_INTERVAL_SECONDS)
        try:
            if supabase_client is None:
                print("Graph refresh skipped: Supabase not connected")
                continue
            enqueue_graph_rebuild_job(True, False)
            print(
                f"Auto-enqueued graph rebuild after {GRAPH_REFRESH_INTERVAL_SECONDS}s "
                "(fuzzy=True, semantic=False)"
            )
        except Exception as exc:
            print(f"Auto graph refresh failed: {exc}")


def start_graph_refresh_scheduler() -> None:
    global graph_refresh_thread_started
    if graph_refresh_thread_started:
        return
    if supabase_client is None:
        return

    try:
        enqueue_graph_rebuild_job(True, False)
        print("Auto-enqueued initial graph rebuild (fuzzy=True, semantic=False)")
    except Exception as exc:
        print(f"Initial graph refresh enqueue failed: {exc}")

    thread = threading.Thread(target=graph_refresh_loop, name="graph-refresh-loop", daemon=True)
    thread.start()
    graph_refresh_thread_started = True
    print(f"Started graph refresh scheduler (interval={GRAPH_REFRESH_INTERVAL_SECONDS}s)")


def run_direct_chat(session: DirectNpcChatSession, user_message: str) -> str:
    recent_history = session.history[-(DIRECT_CHAT_MAX_TURNS * 2):]
    messages = [ChatMessage(role=MessageRole.SYSTEM, content=session.system_prompt)]
    messages.extend(recent_history)
    messages.append(ChatMessage(role=MessageRole.USER, content=user_message))

    response = Settings.llm.chat(messages)
    npc_text = clean_npc_response(extract_chat_text(response))

    session.history.append(ChatMessage(role=MessageRole.USER, content=user_message))
    session.history.append(ChatMessage(role=MessageRole.ASSISTANT, content=npc_text))
    session.history = session.history[-(DIRECT_CHAT_MAX_TURNS * 2):]
    return npc_text


def unload_llm_runtime() -> None:
    """Release the current llama.cpp runtime before loading another LoRA."""
    try:
        Settings.llm = None
    except Exception:
        pass
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


def init_embedding_and_llm() -> None:
    global llm_loaded, llm_load_error
    try:
        Settings.embed_model = HuggingFaceEmbedding(
            model_name=EMBEDDING_MODEL,
            cache_folder=str(Path.home() / ".cache" / "llama_index"),
            local_files_only=True,
        )
        print(f"Loaded embedding model: {EMBEDDING_MODEL}")
    except Exception as exc:
        Settings.embed_model = None
        print(f"Embedding model unavailable, continuing without it: {exc}")

    if not Path(MODEL_PATH).exists():
        llm_loaded = False
        llm_load_error = f"Model file not found: {MODEL_PATH}"
        Settings.llm = None
        print(llm_load_error)
        return

    try:
        model_kwargs = {"n_gpu_layers": LLAMA_N_GPU_LAYERS}
        if active_lora_adapter_path:
            model_kwargs["lora_path"] = active_lora_adapter_path

        Settings.llm = LlamaCPP(
            model_path=MODEL_PATH,
            temperature=LLM_TEMPERATURE,
            max_new_tokens=LLM_MAX_NEW_TOKENS,
            context_window=2048,
            generate_kwargs={
                "stop": STOP_STRINGS,
                "top_p": 0.9,
                "top_k": 40,
                "repeat_penalty": 1.12,
            },
            model_kwargs=model_kwargs,
            verbose=False,
            messages_to_prompt=llama3_messages_to_prompt,
            completion_to_prompt=llama3_completion_to_prompt,
        )
        llm_loaded = True
        llm_load_error = None
        if active_lora_adapter_path:
            print(f"Loaded model: {MODEL_PATH} with LoRA adapter: {active_lora_adapter_path}")
        else:
            print(f"Loaded model: {MODEL_PATH}")
    except Exception as exc:
        llm_loaded = False
        llm_load_error = str(exc)
        Settings.llm = None
        print(f"LLM load error: {exc}")


def load_index() -> object | None:
    global index_loaded, index_load_error
    index_path = Path(INDEX_STORAGE)
    lore_path = Path(LORE_DIR)

    try:
        if index_path.exists():
            storage_context = StorageContext.from_defaults(persist_dir=str(index_path))
            index = load_index_from_storage(storage_context)
            print(f"Loaded LlamaIndex from: {INDEX_STORAGE}")
        else:
            lore_path.mkdir(parents=True, exist_ok=True)
            documents = SimpleDirectoryReader(str(lore_path)).load_data()
            index = VectorStoreIndex.from_documents(documents)
            index.storage_context.persist(persist_dir=str(index_path))
            print(f"Built and persisted LlamaIndex at: {INDEX_STORAGE}")

        index_loaded = True
        index_load_error = None
        return index
    except Exception as exc:
        index_loaded = False
        index_load_error = str(exc)
        print(f"Index load error: {exc}")
        return None


def get_chat_engine(player_id: str, npc_id: str):
    key = f"{player_id}_{npc_id}"
    if key in chat_engines:
        return chat_engines[key]

    system_prompt = apply_memory_slot(build_system_prompt(npc_id), player_id, npc_id)
    session = DirectNpcChatSession(system_prompt=system_prompt)
    chat_engines[key] = session
    return session


def preload_all_npc_models() -> None:
    """Preload all trained NPC LoRA adapters at startup to avoid first-request latency."""
    global MODEL_PATH, active_npc_id, active_lora_adapter_path

    print("Preloading all NPC models...")
    load_npc_model_registry()
    
    preloaded_count = 0
    for npc_id in npc_model_registry.keys():
        try:
            result = select_npc_runtime(npc_id)
            if result.get("loaded"):
                preloaded_count += 1
                print(f"  ✓ Preloaded: {npc_id}")
            else:
                print(f"  ✗ Failed: {npc_id} - {result.get('error', 'unknown error')}")
        except Exception as exc:
            print(f"  ✗ Error preloading {npc_id}: {exc}")
    
    # Reset to base model state after preloading. Some adapters may fail to load
    # under the available VRAM, but that should not leave /status in a failed
    # state when the base model is usable.
    MODEL_PATH = normalize_manifest_path(BASE_MODEL_PATH) or BASE_MODEL_PATH
    active_npc_id = None
    active_lora_adapter_path = None
    chat_engines.clear()
    init_embedding_and_llm()
    
    print(f"Preloaded {preloaded_count}/{len(npc_model_registry)} NPC models")


def on_startup() -> None:
    create_supabase_client()
    global supabase_wrapper
    supabase_wrapper = get_supabase()
    load_npc_model_registry()
    try:
        init_embedding_and_llm()
    except Exception as exc:
        print(f"Startup model initialization error: {exc}")
    try:
        load_index()
    except Exception as exc:
        print(f"Startup index load error: {exc}")
    start_graph_refresh_scheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan manager (modern replacement for on_event)."""
    # Startup
    on_startup()
    if PRELOAD_NPC_MODELS:
        threading.Thread(target=preload_all_npc_models, daemon=True).start()
    yield
    # Shutdown
    print("Shutting down...")


app = FastAPI(title="Game_Surf NPC Dialogue Integrated Server", lifespan=lifespan)

# Add CORS middleware after app creation
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8080", "http://localhost:8080", "http://127.0.0.1", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/status", response_model=StatusResponse)
def status() -> StatusResponse:
    return StatusResponse(
        model_path=MODEL_PATH,
        base_model_path=BASE_MODEL_PATH,
        active_npc_id=active_npc_id,
        active_lora_adapter_path=active_lora_adapter_path,
        model_loaded=llm_loaded,
        index_path=INDEX_STORAGE,
        index_loaded=index_loaded,
        npc_model_registry_size=len(npc_model_registry),
        supabase_enabled=ENABLE_SUPABASE,
        supabase_connected=supabase_client is not None,
        llm_error=llm_load_error,
        index_error=index_load_error,
        gpu_acceleration=get_gpu_acceleration_status(),
    )


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    import time
    start_time = time.time()
    request_stats["total"] += 1

    try:
        with llm_generation_lock:
            runtime = select_npc_runtime(request.npc_id)
            if Settings.llm is None or not runtime.get("loaded"):
                request_stats["errors"] += 1
                raise HTTPException(
                    status_code=503,
                    detail=f"NPC model failed to load for {request.npc_id}: {runtime.get('error') or 'unknown error'}",
                )

            engine = get_chat_engine(request.player_id, request.npc_id)
            if isinstance(engine, DirectNpcChatSession):
                npc_text = run_direct_chat(engine, request.message)
            else:
                response = engine.chat(request.message)
                npc_text = clean_npc_response(str(response))

        # Resolve or create session_id
        session_key = f"{request.player_id}_{request.npc_id}"
        session_id = request.session_id or active_sessions.get(session_key)
        if session_id:
            active_sessions[session_key] = session_id

        if supabase_client is not None:
            try:
                # Create session if none exists
                if not session_id:
                    sess_resp = supabase_client.table("dialogue_sessions").insert({
                        "player_id": request.player_id,
                        "npc_id": request.npc_id,
                        "status": "active",
                    }).execute()
                    if sess_resp.data:
                        session_id = sess_resp.data[0]["session_id"]
                        active_sessions[session_key] = session_id

                # Record the turn
                if session_id:
                    supabase_client.table("dialogue_turns").insert({
                        "session_id": session_id,
                        "player_message": request.message,
                        "npc_response": npc_text,
                        "raw_json": json.dumps({
                            "user": request.message,
                            "npc": npc_text,
                        }),
                    }).execute()
                print(f"Saved turn for session {session_id}")
            except Exception as exc:
                print(f"Supabase write error: {exc}")

        elapsed_ms = (time.time() - start_time) * 1000
        request_stats["total_response_time_ms"] += elapsed_ms

        return ChatResponse(npc_response=npc_text, session_id=session_id)
    except Exception as exc:
        request_stats["errors"] += 1
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream NPC response tokens in real-time using Server-Sent Events (SSE)."""
    async def generate():
        try:
            with llm_generation_lock:
                runtime = select_npc_runtime(request.npc_id)
                if Settings.llm is None or not runtime.get("loaded"):
                    raise RuntimeError(
                        f"NPC model failed to load for {request.npc_id}: {runtime.get('error') or 'unknown error'}"
                    )

                engine = get_chat_engine(request.player_id, request.npc_id)
                
                # For streaming, we'll collect the full response then stream it word-by-word
                # This is a practical compromise since LlamaCPP streaming is complex
                if isinstance(engine, DirectNpcChatSession):
                    npc_text = run_direct_chat(engine, request.message)
                else:
                    response = engine.chat(request.message)
                    npc_text = clean_npc_response(str(response))
            
            # Stream the response word by word with small delays for visual effect
            words = npc_text.split()
            for i, word in enumerate(words):
                # Yield word + space (except for last word)
                chunk = word + (' ' if i < len(words) - 1 else '')
                yield chunk
                # Small delay between words for streaming effect (50ms per word)
                await asyncio.sleep(0.05)
            
            # After streaming response, save to Supabase
            session_key = f"{request.player_id}_{request.npc_id}"
            session_id = request.session_id or active_sessions.get(session_key)
            if session_id:
                active_sessions[session_key] = session_id

            if supabase_client is not None:
                try:
                    # Create session if none exists
                    if not session_id:
                        sess_resp = supabase_client.table("dialogue_sessions").insert({
                            "player_id": request.player_id,
                            "npc_id": request.npc_id,
                            "status": "active",
                        }).execute()
                        if sess_resp.data:
                            session_id = sess_resp.data[0]["session_id"]
                            active_sessions[session_key] = session_id

                    # Record the turn
                    if session_id:
                        supabase_client.table("dialogue_turns").insert({
                            "session_id": session_id,
                            "player_message": request.message,
                            "npc_response": npc_text,
                            "raw_json": json.dumps({
                                "user": request.message,
                                "npc": npc_text,
                            }),
                        }).execute()
                    print(f"Saved turn for session {session_id}")
                except Exception as exc:
                    print(f"Supabase write error: {exc}")
        
        except Exception as exc:
            yield f"ERROR: {str(exc)}"

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/session/start", response_model=StartSessionResponse)
def start_session(request: StartSessionRequest) -> StartSessionResponse:
    """Create a new dialogue session and load prior memory for this player+NPC."""
    print(f"[MEMORY] /session/start called for player_id={request.player_id} npc_id={request.npc_id}")
    session_id: str | None = None
    memory_summary: str | None = None

    if supabase_client is not None:
        try:
            # End any existing active session for this player+NPC
            session_key = f"{request.player_id}_{request.npc_id}"
            old_session_id = active_sessions.get(session_key)
            if not old_session_id:
                active_session_resp = (
                    supabase_client.table("dialogue_sessions")
                    .select("session_id")
                    .match({"player_id": request.player_id, "npc_id": request.npc_id, "status": "active"})
                    .order("started_at", desc=True)
                    .limit(1)
                    .execute()
                )
                if active_session_resp.data:
                    old_session_id = active_session_resp.data[0].get("session_id")
            if old_session_id:
                print(f"[MEMORY] Closing stale active session {old_session_id} for {request.player_id}/{request.npc_id}")
                stale_turns_resp = (
                    supabase_client.table("dialogue_turns")
                    .select("session_id")
                    .eq("session_id", old_session_id)
                    .limit(1)
                    .execute()
                )
                if stale_turns_resp.data:
                    supabase_client.table("dialogue_sessions").update(
                        {"status": "ended", "ended_at": "now()"}
                    ).eq("session_id", old_session_id).execute()
                else:
                    supabase_client.table("dialogue_sessions").delete().eq(
                        "session_id", old_session_id
                    ).execute()
                active_sessions.pop(session_key, None)

            # Create or update the player profile when a name was supplied
            if request.player_name:
                try:
                    supabase_client.table("player_profiles").upsert({
                        "player_id": request.player_id,
                        "display_name": request.player_name,
                    }).execute()
                    print(f"Created/updated player profile for {request.player_id}: {request.player_name}")
                except Exception as exc:
                    print(f"Failed to upsert player profile: {exc}")

            chat_engines.pop(session_key, None)

            # Create new session
            resp = supabase_client.table("dialogue_sessions").insert({
                "player_id": request.player_id,
                "npc_id": request.npc_id,
                "status": "active",
            }).execute()
            if resp.data:
                session_id = resp.data[0]["session_id"]
                active_sessions[session_key] = session_id

            # Load latest memory summary
            print(f"[MEMORY] Loading latest npc_memories summary for {request.player_id}/{request.npc_id}")
            mem_resp = (
                supabase_client.table("npc_memories")
                .select("summary")
                .match({"player_id": request.player_id, "npc_id": request.npc_id})
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            print(f"[MEMORY] /session/start npc_memories rows returned: {len(mem_resp.data) if mem_resp.data else 0}")
            if mem_resp.data:
                memory_summary = mem_resp.data[0]["summary"]
        except Exception as exc:
            print(f"Session start error: {exc}")

    return StartSessionResponse(
        session_id=session_id or str(uuid.uuid4()),
        player_id=request.player_id,
        npc_id=request.npc_id,
        memory_summary=memory_summary,
    )


@app.post("/session/end")
def end_session(request: EndSessionRequest) -> dict:
    """End a dialogue session and persist a summary to npc_memories."""
    if supabase_client is not None:
        try:
            turns_resp = (
                supabase_client.table("dialogue_turns")
                .select("session_id")
                .eq("session_id", request.session_id)
                .limit(1)
                .execute()
            )

            key = f"{request.player_id}_{request.npc_id}"
            chat_engines.pop(key, None)
            active_sessions.pop(key, None)

            if not turns_resp.data:
                supabase_client.table("dialogue_sessions").delete().eq(
                    "session_id", request.session_id
                ).execute()
                return {"status": "discarded_empty", "session_id": request.session_id}

            supabase_client.table("dialogue_sessions").update(
                {"status": "ended", "ended_at": "now()"}
            ).eq("session_id", request.session_id).execute()

            # Enqueue async jobs for GOD memory and graph rebuild
            try:
                enqueue_memory_embedding_job(request.player_id, request.npc_id, request.session_id)
                print(f"Enqueued memory embedding for {request.player_id}/{request.npc_id}")
            except Exception as exc:
                print(f"Failed to enqueue memory embedding: {exc}")

            try:
                enqueue_graph_rebuild_job(True, False)
                print("Enqueued graph rebuild (fuzzy=True, semantic=False)")
            except Exception as exc:
                print(f"Failed to enqueue graph rebuild: {exc}")

        except Exception as exc:
            print(f"Session end error: {exc}")

    return {"status": "ended", "session_id": request.session_id}


@app.get("/session/history/{player_id}/{npc_id}", response_model=SessionHistoryResponse)
def get_session_history(player_id: str, npc_id: str) -> SessionHistoryResponse:
    """Return the most recent active/ended session turns for a player+NPC pair."""
    if supabase_client is None:
        raise HTTPException(status_code=503, detail="Supabase not connected")

    try:
        # Get latest session
        sess_resp = (
            supabase_client.table("dialogue_sessions")
            .select("session_id, player_id, npc_id, status")
            .match({"player_id": player_id, "npc_id": npc_id})
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        if not sess_resp.data:
            return SessionHistoryResponse(session_id="", player_id=player_id, npc_id=npc_id, turns=[])

        session = sess_resp.data[0]
        session_id = session["session_id"]

        turns_resp = (
            supabase_client.table("dialogue_turns")
            .select("player_message, npc_response, created_at")
            .eq("session_id", session_id)
            .order("created_at")
            .execute()
        )
        return SessionHistoryResponse(
            session_id=session_id,
            player_id=player_id,
            npc_id=npc_id,
            turns=turns_resp.data or [],
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/players/{player_id}/memories")
def get_player_memories(player_id: str) -> dict:
    """Return all NPC memory summaries for a player."""
    if supabase_client is None:
        raise HTTPException(status_code=503, detail="Supabase not connected")
    try:
        resp = (
            supabase_client.table("npc_memories")
            .select("npc_id, summary, created_at")
            .eq("player_id", player_id)
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        return {"player_id": player_id, "memories": resp.data or []}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/memory/god")
def get_god_memory(request: GodMemoryRequest) -> GodMemoryResponse:
    """Retrieve GOD memory (semantic memory embeddings) for a player+NPC pair."""
    if supabase_client is None:
        raise HTTPException(status_code=503, detail="Supabase not connected")
    
    try:
        profile_data: dict | None = None
        recent_npc_memories: list[dict] = []
        related_terms: list[dict] = []

        if request.include_profile:
            try:
                profile_resp = (
                    supabase_client.table("player_profiles")
                    .select("player_id, display_name, created_at, updated_at")
                    .eq("player_id", request.player_id)
                    .limit(1)
                    .execute()
                )
                if profile_resp.data:
                    profile_data = profile_resp.data[0]
            except Exception as exc:
                print(f"Profile lookup error: {exc}")

        if request.include_recent_npc_memories:
            try:
                npc_mem_resp = (
                    supabase_client.table("npc_memories")
                    .select("memory_id, player_id, npc_id, summary, raw_json, created_at")
                    .match({"player_id": request.player_id, "npc_id": request.npc_id})
                    .order("created_at", desc=True)
                    .limit(request.limit)
                    .execute()
                )
                recent_npc_memories = npc_mem_resp.data or []
            except Exception as exc:
                print(f"NPC memory lookup error: {exc}")

        if request.include_related_terms:
            try:
                player_node_id = f"player:{request.player_id}"
                edge_resp = (
                    supabase_client.table("relation_graph_edges")
                    .select("source_node_id, target_node_id, edge_type, weight, metadata, created_at")
                    .eq("source_node_id", player_node_id)
                    .eq("edge_type", "uses")
                    .order("weight", desc=True)
                    .limit(request.limit)
                    .execute()
                )
                edges = edge_resp.data or []
                target_ids = [edge.get("target_node_id") for edge in edges if edge.get("target_node_id")]
                node_lookup: dict[str, dict] = {}
                if target_ids:
                    node_resp = (
                        supabase_client.table("relation_graph_nodes")
                        .select("node_id, node_type, label, description")
                        .in_("node_id", target_ids)
                        .execute()
                    )
                    for node in node_resp.data or []:
                        node_lookup[node["node_id"]] = node

                for edge in edges:
                    target_id = edge.get("target_node_id")
                    if not target_id:
                        continue
                    node = node_lookup.get(target_id, {})
                    related_terms.append(
                        {
                            "term": node.get("label") or target_id.removeprefix("term:"),
                            "description": node.get("description"),
                            "edge_type": edge.get("edge_type"),
                            "weight": edge.get("weight"),
                            "messages": (edge.get("metadata") or {}).get("messages", []),
                            "created_at": edge.get("created_at"),
                        }
                    )
            except Exception as exc:
                print(f"Related terms lookup error: {exc}")

        resp = supabase_client.rpc("get_god_memory", {
            "player_id_param": request.player_id,
            "npc_id_param": request.npc_id,
            "query_embedding": None,  # None = fetch all, no filtering
            "limit_count": request.limit,
            "memory_types": request.memory_types or ["session", "encounter"],
        }).execute()

        memories = resp.data if resp.data else []
        return GodMemoryResponse(
            player_id=request.player_id,
            npc_id=request.npc_id,
            profile=profile_data,
            memories=memories,
            recent_npc_memories=recent_npc_memories,
            related_terms=related_terms,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/graph/rebuild")
def rebuild_graph(request: GraphRebuildRequest) -> GraphRebuildResponse:
    """Manually trigger a relation graph rebuild via async queue."""
    if supabase_client is None:
        raise HTTPException(status_code=503, detail="Supabase not connected")
    
    try:
        enqueue_graph_rebuild_job(request.use_fuzzy_match, request.use_semantic_match)
        print(
            "Enqueued graph rebuild job "
            f"(fuzzy={request.use_fuzzy_match}, semantic={request.use_semantic_match})"
        )
        
        return GraphRebuildResponse(
            status="success",
            message=(
                "Graph rebuild job enqueued for processing "
                f"(fuzzy={request.use_fuzzy_match}, semantic={request.use_semantic_match})"
            ),
        )
    except Exception as exc:
        print(f"Failed to enqueue graph rebuild: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/graph/view")
def view_graph() -> dict:
    """Get the current relation graph (nodes and edges)."""
    if supabase_client is None:
        raise HTTPException(status_code=503, detail="Supabase not connected")
    
    try:
        nodes_resp = supabase_client.table("relation_graph_nodes").select("*").execute()
        edges_resp = supabase_client.table("relation_graph_edges").select("*").execute()
        
        return {
            "nodes": nodes_resp.data or [],
            "edges": edges_resp.data or [],
        }
    except Exception as exc:
        # If tables don't exist yet, return empty
        return {
            "nodes": [],
            "edges": [],
            "error": str(exc),
        }


class ReloadModelRequest(BaseModel):
    model_path: str | None = None
    npc_id: str | None = None


def select_npc_runtime(npc_id: str | None = None, model_path: str | None = None) -> dict:
    """Select the shared base model plus the requested NPC LoRA adapter."""
    global MODEL_PATH, active_npc_id, active_lora_adapter_path

    load_npc_model_registry()

    selected_npc = npc_id.strip() if npc_id else None
    selected_model_path = normalize_manifest_path(model_path) if model_path else BASE_MODEL_PATH
    selected_lora_path: str | None = None

    if selected_npc and ENABLE_NPC_LORA:
        selected_lora_path = resolve_lora_adapter_path_for_npc(selected_npc)
        dedicated_gguf = resolve_gguf_model_path_for_npc(selected_npc)
        if selected_lora_path:
            selected_model_path = BASE_MODEL_PATH
        elif dedicated_gguf:
            selected_model_path = dedicated_gguf
        elif selected_npc not in npc_model_registry:
            print(f"No trained adapter manifest found for NPC '{selected_npc}'. Using base model.")
        
        _log_lora_resolution_status(selected_npc, selected_lora_path, selected_model_path)
    elif selected_npc:
        selected_model_path = BASE_MODEL_PATH

    if not selected_model_path:
        selected_model_path = BASE_MODEL_PATH

    normalized_model = normalize_manifest_path(selected_model_path) or selected_model_path
    changed = (
        Path(normalized_model).resolve() != Path(normalize_manifest_path(MODEL_PATH) or MODEL_PATH).resolve()
        or selected_lora_path != active_lora_adapter_path
        or (ENABLE_NPC_LORA and selected_npc != active_npc_id)
    )

    if changed:
        unload_llm_runtime()
        MODEL_PATH = normalized_model
        active_npc_id = selected_npc if ENABLE_NPC_LORA else None
        active_lora_adapter_path = selected_lora_path
        chat_engines.clear()
        init_embedding_and_llm()

    return {
        "model_path": MODEL_PATH,
        "active_npc_id": active_npc_id,
        "active_lora_adapter_path": active_lora_adapter_path,
        "loaded": llm_loaded,
        "error": llm_load_error or "",
    }


@app.post("/reload-model")
def reload_model(request: ReloadModelRequest | None = None) -> dict:
    """Reload the shared model, optionally selecting an NPC LoRA adapter."""
    result = select_npc_runtime(
        npc_id=request.npc_id if request else None,
        model_path=request.model_path if request else None,
    )
    return {
        "status": "model reloaded" if llm_loaded else "model load failed",
        **result,
    }


@app.get("/npc-models")
def list_npc_models() -> dict:
    load_npc_model_registry()
    unique_manifests = {
        manifest.get("_manifest_path", key): manifest
        for key, manifest in npc_model_registry.items()
    }
    return {
        "base_model_path": BASE_MODEL_PATH,
        "active_npc_id": active_npc_id,
        "active_lora_adapter_path": active_lora_adapter_path,
        "models": [npc_runtime_snapshot(manifest) for manifest in unique_manifests.values()],
    }


@app.post("/reload-index")
def reload_index() -> dict[str, str]:
    load_index()
    return {"status": "index reloaded", "index_path": INDEX_STORAGE}


@app.post("/reset-memory")
def reset_memory() -> dict[str, str]:
    chat_engines.clear()
    active_sessions.clear()
    return {"status": "chat memory reset"}


def get_gpu_memory_mb() -> dict | None:
    try:
        import torch
        if torch.cuda.is_available():
            return {
                "allocated_mb": torch.cuda.memory_allocated() / 1024 / 1024,
                "reserved_mb": torch.cuda.memory_reserved() / 1024 / 1024,
                "max_allocated_mb": torch.cuda.max_memory_allocated() / 1024 / 1024,
                "utilization_pct": _get_gpu_utilization(),
            }
    except Exception:
        pass
    return None


def _get_gpu_utilization() -> float:
    """Query current GPU utilization percentage via nvidia-smi."""
    try:
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception:
        pass
    return 0.0


def get_gpu_acceleration_status() -> dict:
    """Check if llama.cpp is actually using GPU acceleration."""
    status = {
        "torch_cuda_available": False,
        "gpu_memory_mb": 0.0,
        "llm_n_gpu_layers": LLAMA_N_GPU_LAYERS,
        "gpu_utilization_pct": 0.0,
    }
    try:
        import torch
        status["torch_cuda_available"] = torch.cuda.is_available()
        if torch.cuda.is_available():
            status["gpu_memory_mb"] = torch.cuda.memory_allocated() / 1024 / 1024
            status["gpu_utilization_pct"] = _get_gpu_utilization()
    except Exception:
        pass
    return status


@app.get("/metrics")
def get_metrics() -> dict:
    avg_response_time = 0
    if request_stats["total"] > 0:
        avg_response_time = request_stats["total_response_time_ms"] / request_stats["total"]

    return {
        "requests_total": request_stats["total"],
        "errors_total": request_stats["errors"],
        "avg_response_time_ms": round(avg_response_time, 2),
        "gpu_memory": get_gpu_memory_mb(),
        "active_sessions": len(active_sessions),
        "active_chat_engines": len(chat_engines),
        "npc_registry_size": len(npc_model_registry),
    }


class DebugSessionResponse(BaseModel):
    session_key: str
    session_id: str | None


@app.get("/debug/sessions")
def debug_sessions() -> dict:
    return {
        "active_sessions": [
            {"session_key": k, "session_id": v}
            for k, v in active_sessions.items()
        ],
        "session_count": len(active_sessions),
    }


@app.get("/debug/npc-state")
def debug_npc_state() -> dict:
    return {
        "active_npc_id": active_npc_id,
        "active_lora_adapter_path": active_lora_adapter_path,
        "model_path": MODEL_PATH,
        "llm_loaded": llm_loaded,
        "llm_error": llm_load_error,
        "gpu_memory": get_gpu_memory_mb(),
        "gpu_acceleration": get_gpu_acceleration_status(),
    }


@app.get("/debug/lora-status/{npc_id}")
def debug_lora_status(npc_id: str) -> dict:
    """Check LoRA adapter status for a specific NPC."""
    load_npc_model_registry()
    manifest = npc_model_registry.get(npc_id)
    
    if not manifest:
        # Try fuzzy match
        for key, m in npc_model_registry.items():
            if npc_id in key or key in npc_id:
                manifest = m
                break
    
    if not manifest:
        return {
            "npc_id": npc_id,
            "found": False,
            "error": f"NPC '{npc_id}' not found in registry. Available: {list(npc_model_registry.keys())}",
        }
    
    adapter_path = resolve_lora_adapter_path_for_npc(npc_id)
    gguf_path = resolve_gguf_model_path_for_npc(npc_id)
    adapter_active = npc_adapter_is_active(npc_id)
    
    return {
        "npc_id": npc_id,
        "found": True,
        "npc_key": manifest.get("npc_key"),
        "artifact_key": manifest.get("artifact_key"),
        "supabase_npc_id": manifest.get("supabase_npc_id"),
        "adapter_path": adapter_path,
        "adapter_exists": Path(adapter_path).exists() if adapter_path else False,
        "adapter_size_mb": round(Path(adapter_path).stat().st_size / 1024 / 1024, 2) if adapter_path and Path(adapter_path).exists() else None,
        "gguf_path": gguf_path,
        "gguf_exists": Path(gguf_path).is_file() if gguf_path else False,
        "adapter_currently_active": adapter_active,
        "runtime_mode": "lora_adapter" if adapter_path else ("dedicated_gguf" if gguf_path else "base_model"),
        "profile": manifest.get("profile", {}),
    }


@app.get("/debug/system-prompt/{npc_id}")
def debug_system_prompt(npc_id: str) -> dict:
    """Get the constructed system prompt for a specific NPC (without memory slot)."""
    system_prompt = build_system_prompt(npc_id)
    return {
        "npc_id": npc_id,
        "system_prompt": system_prompt,
        "system_prompt_length": len(system_prompt),
    }


@app.get("/debug/all-npc-state")
def debug_all_npc_state() -> dict:
    """Get state of all NPC LoRA adapters."""
    load_npc_model_registry()
    states = {}
    for npc_id in sorted(npc_model_registry.keys()):
        manifest = npc_model_registry[npc_id]
        adapter_path = resolve_lora_adapter_path_for_npc(npc_id)
        gguf_path = resolve_gguf_model_path_for_npc(npc_id)
        
        # Check profile match
        profiles_path = TOOLS_LLM_ROOT / "datasets" / "configs" / "npc_profiles.json"
        profile_match = None
        if profiles_path.exists():
            try:
                profiles_data = json.loads(profiles_path.read_text())
                profiles = profiles_data.get("profiles", {})
                prof = profiles.get(npc_id)
                if not prof:
                    for key, value in profiles.items():
                        if npc_id in key or key in npc_id:
                            prof = value
                            break
                profile_match = prof.get("display_name") if prof else None
            except Exception:
                pass
        
        states[npc_id] = {
            "npc_key": manifest.get("npc_key"),
            "artifact_key": manifest.get("artifact_key"),
            "adapter_path": adapter_path,
            "adapter_exists": bool(adapter_path and Path(adapter_path).exists()),
            "adapter_size_mb": round(Path(adapter_path).stat().st_size / 1024 / 1024, 2) if adapter_path and Path(adapter_path).exists() else None,
            "gguf_path": gguf_path,
            "runtime_mode": "lora_adapter" if adapter_path else ("dedicated_gguf" if gguf_path else "base_model"),
            "profile_display_name": profile_match,
        }
    return {
        "active_npc_id": active_npc_id,
        "active_lora_adapter_path": active_lora_adapter_path,
        "gpu_acceleration": get_gpu_acceleration_status(),
        "npcs": states,
    }


@app.get("/debug/memory/{player_id}/{npc_id}")
def debug_player_memory(player_id: str, npc_id: str) -> dict:
    try:
        memory_summary = load_player_context(player_id, npc_id)
        return {
            "player_id": player_id,
            "npc_id": npc_id,
            "memory_context": memory_summary,
        }
    except Exception as exc:
        return {
            "player_id": player_id,
            "npc_id": npc_id,
            "error": str(exc),
        }


@app.post("/debug/clear-history")
def debug_clear_history(request: EndSessionRequest) -> dict:
    key = f"{request.player_id}_{request.npc_id}"
    chat_engines.pop(key, None)
    active_sessions.pop(key, None)
    return {"status": "cleared", "player_id": request.player_id, "npc_id": request.npc_id}


@app.post("/debug/clear-all-sessions")
def debug_clear_all_sessions() -> dict:
    count = len(active_sessions)
    chat_engines.clear()
    active_sessions.clear()
    return {"status": "cleared_all", "count": count}


class ReloadNpcRequest(BaseModel):
    npc_id: str


@app.post("/reload-npc")
def reload_npc(request: ReloadNpcRequest | None = None) -> dict:
    npc_id = request.npc_id if request else None
    result = select_npc_runtime(npc_id=npc_id)
    return {
        "status": "ok" if llm_loaded else "error",
        "active_npc_id": active_npc_id,
        "active_lora_adapter_path": active_lora_adapter_path,
        **result,
    }


class ClearPlayerMemoryRequest(BaseModel):
    player_id: str


@app.post("/clear-player-memory")
def clear_player_memory(request: ClearPlayerMemoryRequest) -> dict:
    keys_to_remove = [k for k in chat_engines.keys() if k.startswith(request.player_id)]
    for key in keys_to_remove:
        chat_engines.pop(key, None)
    return {"status": "cleared", "player_id": request.player_id, "removed_keys": keys_to_remove}


HTML_TEST_PAGE = '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>10-Player Memory Test</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1a1a2e; color: #eee; padding: 20px; }
        .container { max-width: 900px; margin: 0 auto; }
        h1 { color: #00d4ff; margin-bottom: 20px; }
        .card { background: #16213e; border-radius: 12px; padding: 24px; margin-bottom: 20px; }
        .form-group { margin-bottom: 16px; }
        label { display: block; margin-bottom: 6px; color: #00d4ff; font-weight: 500; }
        input, select, textarea { width: 100%; padding: 12px; border: 1px solid #0f3460; border-radius: 8px; background: #0f3460; color: #eee; font-size: 14px; }
        textarea { min-height: 80px; resize: vertical; font-family: inherit; }
        input:focus, select:focus, textarea:focus { outline: none; border-color: #00d4ff; }
        button { background: #00d4ff; color: #1a1a2e; border: none; padding: 14px 28px; border-radius: 8px; font-size: 16px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
        button:hover { background: #00b8e6; transform: translateY(-1px); }
        button:disabled { background: #555; cursor: not-allowed; }
        button.stop { background: #e94560; }
        button.stop:hover { background: #d63850; }
        .progress-bar { background: #0f3460; border-radius: 8px; height: 24px; overflow: hidden; margin: 16px 0; }
        .progress-fill { background: linear-gradient(90deg, #00d4ff, #00b8e6); height: 100%; transition: width 0.3s; width: 0%; }
        .status-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin: 16px 0; }
        .status-item { background: #0f3460; padding: 12px; border-radius: 8px; }
        .status-label { font-size: 12px; color: #888; }
        .status-value { font-size: 18px; font-weight: 600; color: #00d4ff; }
        .log { background: #0f3460; border-radius: 8px; padding: 16px; max-height: 400px; overflow-y: auto; font-family: 'Monaco', 'Menlo', monospace; font-size: 13px; }
        .log-entry { padding: 4px 0; border-bottom: 1px solid #1a1a2e; }
        .log-entry:first-child { border-top: none; }
        .log-time { color: #888; margin-right: 8px; }
        .log-player { color: #00d4ff; font-weight: 600; }
        .log-message { color: #aaa; }
        .log-response { color: #4ade80; }
        .player-row { display: flex; align-items: center; padding: 8px; margin: 4px 0; background: #0f3460; border-radius: 6px; }
        .player-row.current { border: 2px solid #00d4ff; }
        .player-num { font-weight: 600; margin-right: 12px; color: #00d4ff; min-width: 30px; }
        .player-name { flex: 1; }
        .player-status { color: #888; }
        .player-status.done { color: #4ade80; }
        .player-status.error { color: #e94560; }
        .summary { background: #0f3460; padding: 16px; border-radius: 8px; margin-top: 16px; }
        .summary h3 { color: #00d4ff; margin-bottom: 12px; }
        .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; }
        .summary-item { text-align: center; }
        .summary-value { font-size: 24px; font-weight: 700; }
        .summary-label { font-size: 12px; color: #888; }
        .npc-card { background: #0f3460; border-radius: 8px; padding: 16px; margin-bottom: 16px; border: 2px solid transparent; }
        .cross-session-note { background: #0a2a1a; border: 1px solid #2d6a4f; border-radius: 6px; padding: 10px 14px; font-size: 12px; color: #4ade80; }
        .npc-card.enabled { border-color: #00d4ff; }
        .npc-header { display: flex; align-items: center; margin-bottom: 12px; }
        .npc-header input[type="checkbox"] { width: auto; margin-right: 10px; }
        .npc-header label { margin: 0; font-size: 16px; color: #00d4ff; cursor: pointer; }
        .npc-fields { opacity: 0.5; pointer-events: none; }
        .npc-fields.active { opacity: 1; pointer-events: auto; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎮 10-Player Memory Test</h1>
        
        <div class="card" id="configCard">
            <h2 style="margin-bottom: 16px;">Configure Test</h2>
            <form id="testForm">
                <div class="form-group">
                    <label>Player Name Base</label>
                    <input type="text" id="playerName" placeholder="e.g., Player" value="TestPlayer">
                    <small style="color: #888;">Test will create player_001, player_002, etc. for each NPC</small>
                </div>
                
                <div class="form-group">
                    <label>Players per NPC</label>
                    <input type="number" id="numPlayers" value="3" min="1" max="20">
                    <small style="color: #888;">Number of players to simulate for EACH enabled NPC</small>
                </div>
                
                <div class="form-group">
                    <label style="color: #4ade80;">
                        <input type="checkbox" id="crossSession" style="width: auto; margin-right: 8px;">
                        Cross-Session Memory Test
                    </label>
                    <small style="color: #888;">Phase 1: msg1 → end session. Phase 2: msg2 in NEW session (validates memory persistence). Slower but tests full pipeline.</small>
                </div>
                
                <h3 style="margin: 24px 0 16px; color: #00d4ff;">NPC Configuration</h3>
                <p style="color: #888; margin-bottom: 16px;">Enable NPCs and configure their messages. Each enabled NPC will run separately.</p>
                
                <div class="npc-card enabled" id="npc-card-ai_news_instructor">
                    <div class="npc-header">
                        <input type="checkbox" id="enable-ai_news_instructor" value="ai_news_instructor" checked>
                        <label for="enable-ai_news_instructor">🤖 AI News Analyst</label>
                    </div>
                    <div class="npc-fields active" id="fields-ai_news_instructor">
                        <div class="form-group">
                            <label>Message 1</label>
                            <textarea id="msg1-ai_news_instructor" placeholder="First message for AI News...">What are the latest AI breakthroughs?</textarea>
                        </div>
                        <div class="form-group">
                            <label>Message 2</label>
                            <textarea id="msg2-ai_news_instructor" placeholder="Second message for AI News...">Tell me about GPT-5</textarea>
                        </div>
                    </div>
                </div>
                
                <div class="npc-card" id="npc-card-maestro_jazz_instructor">
                    <div class="npc-header">
                        <input type="checkbox" id="enable-maestro_jazz_instructor" value="maestro_jazz_instructor">
                        <label for="enable-maestro_jazz_instructor">🎷 The Maestro (Jazz)</label>
                    </div>
                    <div class="npc-fields" id="fields-maestro_jazz_instructor">
                        <div class="form-group">
                            <label>Message 1</label>
                            <textarea id="msg1-maestro_jazz_instructor" placeholder="First message for Jazz..."></textarea>
                        </div>
                        <div class="form-group">
                            <label>Message 2</label>
                            <textarea id="msg2-maestro_jazz_instructor" placeholder="Second message for Jazz..."></textarea>
                        </div>
                    </div>
                </div>
                
                <div class="npc-card" id="npc-card-llm_instructor">
                    <div class="npc-header">
                        <input type="checkbox" id="enable-llm_instructor" value="llm_instructor">
                        <label for="enable-llm_instructor">🧠 Professor LoRA</label>
                    </div>
                    <div class="npc-fields" id="fields-llm_instructor">
                        <div class="form-group">
                            <label>Message 1</label>
                            <textarea id="msg1-llm_instructor" placeholder="First message for LLM..."></textarea>
                        </div>
                        <div class="form-group">
                            <label>Message 2</label>
                            <textarea id="msg2-llm_instructor" placeholder="Second message for LLM..."></textarea>
                        </div>
                    </div>
                </div>
                
                <div class="npc-card" id="npc-card-marvel_comics_instructor">
                    <div class="npc-header">
                        <input type="checkbox" id="enable-marvel_comics_instructor" value="marvel_comics_instructor">
                        <label for="enable-marvel_comics_instructor">🦸 MarvelOracle</label>
                    </div>
                    <div class="npc-fields" id="fields-marvel_comics_instructor">
                        <div class="form-group">
                            <label>Message 1</label>
                            <textarea id="msg1-marvel_comics_instructor" placeholder="First message for Marvel..."></textarea>
                        </div>
                        <div class="form-group">
                            <label>Message 2</label>
                            <textarea id="msg2-marvel_comics_instructor" placeholder="Second message for Marvel..."></textarea>
                        </div>
                    </div>
                </div>
                
                <div class="npc-card" id="npc-card-supabase_instructor">
                    <div class="npc-header">
                        <input type="checkbox" id="enable-supabase_instructor" value="supabase_instructor">
                        <label for="enable-supabase_instructor">💾 Professor Supabase</label>
                    </div>
                    <div class="npc-fields" id="fields-supabase_instructor">
                        <div class="form-group">
                            <label>Message 1</label>
                            <textarea id="msg1-supabase_instructor" placeholder="First message for Supabase..."></textarea>
                        </div>
                        <div class="form-group">
                            <label>Message 2</label>
                            <textarea id="msg2-supabase_instructor" placeholder="Second message for Supabase..."></textarea>
                        </div>
                    </div>
                </div>
                
                <div class="npc-card" id="npc-card-kosmos_instructor">
                    <div class="npc-header">
                        <input type="checkbox" id="enable-kosmos_instructor" value="kosmos_instructor">
                        <label for="enable-kosmos_instructor">🏛️ Professor Kosmos</label>
                    </div>
                    <div class="npc-fields" id="fields-kosmos_instructor">
                        <div class="form-group">
                            <label>Message 1</label>
                            <textarea id="msg1-kosmos_instructor" placeholder="First message for Greek Mythology..."></textarea>
                        </div>
                        <div class="form-group">
                            <label>Message 2</label>
                            <textarea id="msg2-kosmos_instructor" placeholder="Second message for Greek Mythology..."></textarea>
                        </div>
                    </div>
                </div>
                
                <button type="submit" id="startBtn">Start Test</button>
            </form>
        </div>
        
        <div class="card" id="progressCard" style="display: none;">
            <h2>Progress</h2>
            <div class="cross-session-note" id="crossNote" style="display: none;">Cross-Session Mode: Phase 1 complete — waiting for memory processing before Phase 2 (msg2 in NEW sessions)</div>
            
            <div class="progress-bar">
                <div class="progress-fill" id="progressFill"></div>
            </div>
            
            <div class="status-grid">
                <div class="status-item">
                    <div class="status-label">Current Player</div>
                    <div class="status-value" id="currentPlayer">--</div>
                </div>
                <div class="status-item">
                    <div class="status-label">Session Status</div>
                    <div class="status-value" id="sessionStatus">--</div>
                </div>
                <div class="status-item">
                    <div class="status-label">Completed</div>
                    <div class="status-value" id="completed">0/10</div>
                </div>
                <div class="status-item">
                    <div class="status-label">Elapsed Time</div>
                    <div class="status-value" id="elapsedTime">0:00</div>
                </div>
            </div>
            
            <div class="log" id="log"></div>
            
            <button class="stop" id="stopBtn" style="margin-top: 16px;">Stop Test</button>
        </div>
        
        <div class="card" id="summaryCard" style="display: none;">
            <h2>Test Results</h2>
            
            <div class="summary">
                <div class="summary-grid">
                    <div class="summary-item">
                        <div class="summary-value" id="totalPlayers">0</div>
                        <div class="summary-label">Total Players</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value" id="successfulPlayers">0</div>
                        <div class="summary-label">Successful</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value" id="failedPlayers">0</div>
                        <div class="summary-label">Failed</div>
                    </div>
                    <div class="summary-item">
                        <div class="summary-value" id="memoriesCreated">0</div>
                        <div class="summary-label">Memories Created</div>
                    </div>
                </div>
            </div>
            
            <h3 style="margin: 20px 0 12px;">Player Details</h3>
            <div id="playerDetails"></div>
            
            <button onclick="location.reload()" style="margin-top: 20px;">Run New Test</button>
        </div>
    </div>
    
    <script>
        const form = document.getElementById('testForm');
        const startBtn = document.getElementById('startBtn');
        const stopBtn = document.getElementById('stopBtn');
        
        let pollInterval;
        
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            // Build NPCs config
            const npcs = [];
            ['ai_news_instructor', 'maestro_jazz_instructor', 'llm_instructor', 'marvel_comics_instructor', 'supabase_instructor', 'kosmos_instructor'].forEach(npc => {
                const checkbox = document.getElementById('enable-' + npc);
                if (checkbox && checkbox.checked) {
                    const msg1 = document.getElementById('msg1-' + npc).value;
                    const msg2 = document.getElementById('msg2-' + npc).value;
                    if (msg1.trim() || msg2.trim()) {
                        npcs.push({
                            npc_id: npc,
                            message_1: msg1,
                            message_2: msg2
                        });
                    }
                }
            });
            
            if (npcs.length === 0) {
                alert('Please enable at least one NPC and enter messages');
                return;
            }
            
            const config = {
                player_name: document.getElementById('playerName').value || 'TestPlayer',
                npcs: npcs,
                num_players: parseInt(document.getElementById('numPlayers').value) || 3,
                cross_session: document.getElementById('crossSession').checked
            };
            
            startBtn.disabled = true;
            startBtn.textContent = 'Starting...';
            
            try {
                const resp = await fetch('/api/start-test', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(config)
                });
                
                if (!resp.ok) {
                    const err = await resp.json();
                    alert('Failed to start test: ' + (err.detail || 'Unknown error'));
                    startBtn.disabled = false;
                    startBtn.textContent = 'Start Test';
                    return;
                }
                
                document.getElementById('configCard').style.display = 'none';
                document.getElementById('progressCard').style.display = 'block';
                
                startPolling();
            } catch (err) {
                alert('Error: ' + err.message);
                startBtn.disabled = false;
                startBtn.textContent = 'Start Test';
            }
        });
        
        // NPC checkbox toggle
        ['ai_news_instructor', 'maestro_jazz_instructor', 'llm_instructor', 'marvel_comics_instructor', 'supabase_instructor', 'kosmos_instructor'].forEach(npc => {
            const checkbox = document.getElementById('enable-' + npc);
            const card = document.getElementById('npc-card-' + npc);
            const fields = document.getElementById('fields-' + npc);
            if (checkbox && card && fields) {
                checkbox.addEventListener('change', () => {
                    if (checkbox.checked) {
                        card.classList.add('enabled');
                        fields.classList.add('active');
                    } else {
                        card.classList.remove('enabled');
                        fields.classList.remove('active');
                    }
                });
            }
        });
        
        stopBtn.addEventListener('click', async () => {
            await fetch('/api/stop-test', { method: 'POST' });
        });
        
        function startPolling() {
            pollInterval = setInterval(pollStatus, 1000);
        }
        
        async function pollStatus() {
            try {
                const resp = await fetch('/api/test-status');
                const state = await resp.json();
                
                if (!state.running && state.results.length > 0) {
                    clearInterval(pollInterval);
                    showSummary(state);
                    return;
                }
                
                updateUI(state);
            } catch (err) {
                console.error('Poll error:', err);
            }
        }
        
        function updateUI(state) {
            const results = state.results || [];
            const total = state.total_expected || results.length;
            const current = state.current_player || 0;
            const last_update = state.last_update || {};
            const phase = state.phase || 'Phase 1';
            
            // Show cross-session banner
            const crossNote = document.getElementById('crossNote');
            if (state.cross_session) {
                crossNote.style.display = 'block';
                crossNote.textContent = phase + ' — ' + (results.length) + '/' + total + ' done | ' +
                    (state.current_npc || '') + ' p' + current;
            }
            
            document.getElementById('progressFill').style.width = (current / total * 100) + '%';
            document.getElementById('currentPlayer').textContent = state.current_npc ? state.current_npc + ' (' + current + ')' : '--';
            document.getElementById('completed').textContent = results.length + '/' + total;
            
            if (state.start_time) {
                const elapsed = Math.floor((Date.now() - state.start_time) / 1000);
                const mins = Math.floor(elapsed / 60);
                const secs = elapsed % 60;
                document.getElementById('elapsedTime').textContent = mins + ':' + String(secs).padStart(2, '0');
            }
            
            if (last_update.player_id) {
                if (last_update.session_status) {
                    document.getElementById('sessionStatus').textContent = last_update.session_status;
                }
                
                const log = document.getElementById('log');
                const entries = [
                    '<div class="log-entry"><span class="log-time">[' + new Date().toLocaleTimeString() + ']</span> ' +
                    '<span class="log-player">' + last_update.player_id + '</span>: ' +
                    '<span class="log-message">' + (last_update.last_message || '') + '</span></div>'
                ];
                
                if (last_update.last_response) {
                    const respText = last_update.last_response.substring(0, 100);
                    entries.push(
                        '<div class="log-entry"><span class="log-time">--></span> ' +
                        '<span class="log-response">' + respText + (last_update.last_response.length > 100 ? '...' : '') + '</span></div>'
                    );
                }
                
                log.innerHTML = entries.join('') + log.innerHTML;
            }
        }
        
        function showSummary(state) {
            document.getElementById('progressCard').style.display = 'none';
            document.getElementById('summaryCard').style.display = 'block';
            
            const results = state.results || [];
            const successful = results.filter(r => !r.error).length;
            const failed = results.filter(r => r.error).length;
            const memories = results.filter(r => r.memory_created).length;
            
            document.getElementById('totalPlayers').textContent = results.length;
            document.getElementById('successfulPlayers').textContent = successful;
            document.getElementById('failedPlayers').textContent = failed;
            document.getElementById('memoriesCreated').textContent = memories;
            
            const details = document.getElementById('playerDetails');
            details.innerHTML = results.map(r => 
                '<div class="player-row ' + (r.error ? 'error' : '') + '">' +
                    '<span class="player-num">' + r.player_id.replace('player_', '') + '</span>' +
                    '<span class="player-name">' + r.player_name + '</span>' +
                    '<span class="player-status ' + (r.error ? 'error' : 'done') + '">' + (r.error || (r.memory_created ? '✓ Memory' : 'Session done')) + '</span>' +
                '</div>'
            ).join('');
        }
    </script>
</body>
</html>
'''

import time

test_state: dict = {
    "running": False,
    "config": None,
    "current_player": 0,
    "current_npc": None,
    "total_expected": 0,
    "results": [],
    "start_time": None,
    "last_update": None,
    "phase": "normal",
    "cross_session": False,
}
_test_lock = threading.Lock()


class NpcTestConfig(BaseModel):
    npc_id: str
    message_1: str
    message_2: str
    cross_session: bool = False  # Phase 1 ends session → Phase 2 in new session (memory test)


class TestConfig(BaseModel):
    player_name: str
    npcs: list[NpcTestConfig]
    num_players: int = 3
    cross_session: bool = False  # If True: Phase 1=msg1→end, wait; Phase 2=msg2 in NEW session (memory test)


def set_test_update(**updates) -> None:
    with _test_lock:
        last_update = dict(test_state.get("last_update") or {})
        last_update.update(updates)
        test_state["last_update"] = last_update


def check_server_health() -> bool:
    global app
    try:
        for route in app.routes:
            if hasattr(route, 'path') and route.path == '/health':
                return True
        return True
    except Exception:
        return True


def start_session_sync(player_id: str, player_name: str, npc_id: str) -> Optional[dict]:
    try:
        resp = requests.post(
            f"{BASE_URL}/session/start",
            json={"player_id": player_id, "player_name": player_name, "npc_id": npc_id},
            timeout=10
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def send_chat_sync(player_id: str, npc_id: str, message: str, session_id: str) -> Optional[dict]:
    try:
        resp = requests.post(
            f"{BASE_URL}/chat",
            json={"player_id": player_id, "npc_id": npc_id, "message": message, "session_id": session_id},
            timeout=60
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def end_session_sync(session_id: str, player_id: str, npc_id: str) -> bool:
    try:
        resp = requests.post(
            f"{BASE_URL}/session/end",
            json={"session_id": session_id, "player_id": player_id, "npc_id": npc_id},
            timeout=10
        )
        return resp.status_code == 200
    except Exception:
        return False


def get_memory_sync(player_id: str, npc_id: str) -> Optional[dict]:
    try:
        resp = requests.get(f"{BASE_URL}/debug/memory/{player_id}/{npc_id}", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            memory_context = data.get("memory_context") or data.get("memory_summary") or ""
            if memory_context and memory_context != "No saved player memory.":
                return data
        return None
    except Exception:
        return None


def get_session_history_sync(player_id: str, npc_id: str) -> Optional[dict]:
    try:
        resp = requests.get(f"{BASE_URL}/session/history/{player_id}/{npc_id}", timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


# Character-specific probe messages for identity verification
# Use TEACHING questions instead of name questions, since some NPCs have refusal styles
# that prevent them from stating their names directly.
_NPC_PROBE_MESSAGES: dict[str, str] = {
    "ai_news_instructor": "What is a recent AI breakthrough you can tell me about?",
    "maestro_jazz_instructor": "Tell me about a famous jazz musician.",
    "llm_instructor": "What is LoRA and how does it work?",
    "marvel_comics_instructor": "Who is your favorite Avenger and why?",
    "supabase_instructor": "What is PostgreSQL and why use it?",
    "kosmos_instructor": "Tell me about a Greek god.",
}

# Expected name fragments for identity verification
# kosmos_instructor: include "whispers", "sage", "olympus", "cosmos" (all appear in LoRA responses)
_NPC_NAME_PATTERNS: dict[str, list[str]] = {
    "ai_news_instructor": ["ai news", "analyst"],
    "maestro_jazz_instructor": ["maestro", "jazz"],
    "llm_instructor": ["lora", "loRA"],
    "marvel_comics_instructor": ["marvel", "oracle", "marveloracle"],
    "supabase_instructor": ["supabase"],
    "kosmos_instructor": ["kosmos", "sage", "olympus", "whispers", "cosmos"],
}


def verify_npc_identity(npc_id: str, response: str) -> dict:
    """Verify that the NPC response matches the expected identity.
    
    Logic: correct match first. Only flag wrong if no correct match AND a generic
    unhelpful-pattern is detected. Never penalize "analyst" in AI News Analyst.
    """
    if not response:
        return {"verified": False, "reason": "empty response"}
    
    response_lower = response.lower()
    patterns = _NPC_NAME_PATTERNS.get(npc_id, [npc_id.replace("_", " ")])
    
    matched = [p for p in patterns if p in response_lower]
    partial = [p for p in patterns if any(word in response_lower for word in p.split())]
    
    # Is this a correct match?
    if matched:
        return {
            "verified": True,
            "matched_patterns": matched,
            "partial_matches": partial,
            "is_wrong_identity": False,
            "response_preview": response[:200],
        }
    
    # No correct match found — check for wrong/generic identity
    # Only flag "analyst" as wrong if the correct pattern ("ai news") isn't present.
    # This avoids false-positives like "I'm AI News Analyst" scoring "analyst" as wrong.
    wrong_generic = [
        "helpful npc", "helpful ai", "helpful assistant",
        "i'm an ai", "i am an ai",
    ]
    is_generic = any(p in response_lower for p in wrong_generic)
    
    # Flag "analyst" as wrong ONLY for non-ai-news NPCs
    is_wrong_analyst = (
        "analyst" in response_lower
        and npc_id != "ai_news_instructor"
        and "ai news" not in response_lower
    )
    
    is_wrong = is_generic or is_wrong_analyst
    
    return {
        "verified": False,
        "matched_patterns": matched,
        "partial_matches": partial,
        "is_wrong_identity": is_wrong,
        "response_preview": response[:200],
    }


def probe_npc_identity_sync(npc_id: str) -> Optional[dict]:
    """Quickly probe an NPC's identity with a character-specific question.
    
    Calls the chat logic DIRECTLY (not via HTTP) to avoid single-threaded timeout.
    """
    probe_msg = _NPC_PROBE_MESSAGES.get(npc_id)
    if not probe_msg:
        return None

    try:
        # Select NPC runtime and get chat engine directly (no HTTP sub-request)
        select_npc_runtime(npc_id)
        if Settings.llm is None:
            return {"npc_id": npc_id, "error": "LLM not loaded"}

        engine = get_chat_engine("__probe__", npc_id)
        if isinstance(engine, DirectNpcChatSession):
            npc_response = run_direct_chat(engine, probe_msg)
        else:
            response = engine.chat(probe_msg)
            npc_response = clean_npc_response(str(response))

        identity_check = verify_npc_identity(npc_id, npc_response)
        return {
            "npc_id": npc_id,
            "probe_message": probe_msg,
            "npc_response": npc_response[:300],
            "identity_check": identity_check,
        }
    except Exception as e:
        return {"npc_id": npc_id, "error": str(e)}
    except Exception as e:
        return {"npc_id": npc_id, "error": str(e)}


def get_all_npc_lora_status_sync() -> dict:
    """Get LoRA status for all NPCs at once."""
    results = {}
    for npc_id in ["ai_news_instructor", "maestro_jazz_instructor", "llm_instructor", 
                   "marvel_comics_instructor", "supabase_instructor", "kosmos_instructor"]:
        try:
            resp = requests.get(f"{BASE_URL}/debug/lora-status/{npc_id}", timeout=5)
            if resp.status_code == 200:
                results[npc_id] = resp.json()
        except Exception:
            results[npc_id] = {"error": "failed to fetch"}
    return results


def get_player_memories_sync(player_id: str) -> Optional[dict]:
    try:
        resp = requests.get(f"{BASE_URL}/players/{player_id}/memories", timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def get_god_memory_sync(player_id: str, npc_id: str) -> Optional[dict]:
    try:
        resp = requests.post(
            f"{BASE_URL}/memory/god",
            json={
                "player_id": player_id,
                "npc_id": npc_id,
                "limit": 5,
                "include_profile": True,
                "include_recent_npc_memories": True,
                "include_related_terms": True,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def trigger_graph_rebuild_sync() -> bool:
    try:
        resp = requests.post(
            f"{BASE_URL}/graph/rebuild",
            json={"use_fuzzy_match": True, "use_semantic_match": False},
            timeout=15,
        )
        return resp.status_code == 200
    except Exception:
        return False


def run_player_session_thread(player_idx: int, player_id: str, player_name: str, npc_id: str, messages: list[str], fresh_session: bool = False):
    global test_state
    
    result = {
        "player_id": player_id,
        "player_name": player_name,
        "session_id": None,
        "npc_id": npc_id,
        "messages_sent": messages,
        "responses_received": [],
        "memory_created": False,
        "memory_loaded_on_start": False,
        "history_verified": False,
        "player_memories_verified": False,
        "god_memory_verified": False,
        "identity_verified": None,
        "turn_count": 0,
        "duration_seconds": 0,
        "error": None,
    }
    
    start_time = time.time()
    
    try:
        session_resp = start_session_sync(player_id, player_name, npc_id)
        if not session_resp:
            result["error"] = "Failed to start session"
            with _test_lock:
                test_state["results"].append(result)
            return
        
        session_id = session_resp.get("session_id")
        result["session_id"] = session_id
        result["memory_loaded_on_start"] = bool(session_resp.get("memory_summary"))
        set_test_update(
            player_id=player_id,
            npc_id=npc_id,
            session_status="started",
            last_message=f"Session {session_id[:8]}..." if session_id else "N/A",
            memory_loaded_on_start=result["memory_loaded_on_start"],
        )
        
        time.sleep(1)
        
        # First: send actual messages
        for i, msg in enumerate(messages):
            if msg and msg.strip():
                set_test_update(
                    player_id=player_id,
                    npc_id=npc_id,
                    session_status=f"sending message {i+1}/{len(messages)}",
                    last_message=msg,
                    last_response=None,
                )
                
                chat_resp = send_chat_sync(player_id, npc_id, msg, session_id)
                if not chat_resp:
                    result["error"] = f"Failed on message {i+1}"
                    break
                
                npc_response = chat_resp.get("npc_response", "")
                result["responses_received"].append(npc_response)
                result["turn_count"] += 1
                set_test_update(last_response=npc_response)

                time.sleep(TEST_MESSAGE_DELAY_SECONDS)
        
        # Identity probe: verify the NPC has the right persona
        if not result["error"] and npc_id in _NPC_PROBE_MESSAGES:
            set_test_update(session_status="probing identity", last_message="[identity probe]")
            probe_resp = send_chat_sync(player_id, npc_id, _NPC_PROBE_MESSAGES[npc_id], session_id)
            if probe_resp:
                probe_response = probe_resp.get("npc_response", "")
                identity_check = verify_npc_identity(npc_id, probe_response)
                result["identity_verified"] = identity_check
                set_test_update(
                    session_status="identity check done",
                    identity_verified=identity_check.get("verified"),
                    last_response=f"ID:{identity_check.get('verified')} {probe_response[:80]}"
                )
            time.sleep(TEST_IDENTITY_PROBE_DELAY_SECONDS)
        
        if not result["error"]:
            history = get_session_history_sync(player_id, npc_id)
            result["history_verified"] = bool(history and len(history.get("turns") or []) >= result["turn_count"])
            set_test_update(session_status="ending session", history_verified=result["history_verified"])
            
            if end_session_sync(session_id, player_id, npc_id):
                set_test_update(session_status="waiting for memory processing")
                time.sleep(TEST_MEMORY_PROCESSING_DELAY_SECONDS)
                
                memory = get_memory_sync(player_id, npc_id)
                result["memory_created"] = memory is not None
                player_memories = get_player_memories_sync(player_id)
                result["player_memories_verified"] = bool(
                    player_memories
                    and any(m.get("npc_id") == npc_id for m in player_memories.get("memories", []))
                )
                god_memory = get_god_memory_sync(player_id, npc_id)
                result["god_memory_verified"] = bool(
                    god_memory
                    and (
                        god_memory.get("profile")
                        or god_memory.get("recent_npc_memories")
                        or god_memory.get("memories")
                    )
                )
                set_test_update(
                    session_status="memory checks complete",
                    memory_created=result["memory_created"],
                    player_memories_verified=result["player_memories_verified"],
                    god_memory_verified=result["god_memory_verified"],
                )
            else:
                result["error"] = "Failed to end session"
        
    except Exception as e:
        result["error"] = str(e)
        if not result.get("session_id"):
            with _test_lock:
                test_state["results"].append(result)
            return
    
    result["duration_seconds"] = time.time() - start_time
    with _test_lock:
        test_state["results"].append(result)


def run_full_test_thread(config: dict):
    global test_state
    
    player_name_base = config.get("player_name", "Player")
    npc_configs = config.get("npcs", [])
    num_players = config.get("num_players", 3)
    cross_session = config.get("cross_session", False)
    
    if not npc_configs:
        test_state["running"] = False
        return
    
    test_state["total_expected"] = len(npc_configs) * num_players * (2 if cross_session else 1)
    test_state["cross_session"] = cross_session
    set_test_update(
        player_id="---",
        npc_id="---",
        session_status="checking server and Supabase",
        last_message="Running preflight checks...",
    )
    status_ok = False
    try:
        status_resp = requests.get(f"{BASE_URL}/status", timeout=10)
        status_data = status_resp.json() if status_resp.status_code == 200 else {}
        status_ok = bool(status_data.get("supabase_enabled") and status_data.get("supabase_connected"))
    except Exception:
        status_ok = False
    if not check_server_health() or not status_ok:
        with _test_lock:
            test_state["results"].append({
                "player_id": "preflight",
                "player_name": player_name_base,
                "session_id": None,
                "npc_id": None,
                "turn_count": 0,
                "memory_created": False,
                "memory_loaded_on_start": False,
                "history_verified": False,
                "player_memories_verified": False,
                "god_memory_verified": False,
                "duration_seconds": 0,
                "error": "Preflight failed: server healthy but Supabase is not enabled/connected",
            })
            test_state["running"] = False
            test_state["phase"] = "failed"
        return
    
    # Cross-session: Phase 1 = msg1 for all, wait, Phase 2 = msg2 for all
    if cross_session:
        for phase in ["Phase 1", "Phase 2"]:
            test_state["phase"] = phase
            
            for npc_idx, npc_config in enumerate(npc_configs):
                if not test_state["running"]:
                    break
                
                npc_id = npc_config["npc_id"]
                # Phase 1 → message_1, Phase 2 → message_2
                msg_idx = 0 if phase == "Phase 1" else 1
                messages = [
                    npc_config.get("message_1", ""),
                    npc_config.get("message_2", ""),
                ]
                target_msg = messages[msg_idx]
                
                if not target_msg or not target_msg.strip():
                    continue
                
                test_state["current_npc"] = npc_id
                
                for i in range(1, num_players + 1):
                    if not test_state["running"]:
                        break
                    
                    test_state["current_player"] = i
                    player_id = f"{player_name_base}_{npc_id}_{str(i).zfill(3)}"
                    player_name = f"{player_name_base} {i}"
                    
                    # Phase 2: always fresh session (cleared between phases)
                    fresh_session = (phase == "Phase 2")
                    
                    thread = threading.Thread(
                        target=run_player_session_thread,
                        args=(i, player_id, player_name, npc_id, [target_msg], fresh_session)
                    )
                    thread.start()
                    thread.join()
                    
                    if i < num_players and test_state["running"]:
                        time.sleep(TEST_PLAYER_DELAY_SECONDS)
                
                if npc_idx < len(npc_configs) - 1 and test_state["running"]:
                    time.sleep(TEST_NPC_SWITCH_DELAY_SECONDS)
            
            # After Phase 1: wait for memory processing before Phase 2
            if phase == "Phase 1" and test_state["running"]:
                with _test_lock:
                    test_state["last_update"] = {
                        "player_id": "---",
                        "npc_id": "---",
                        "session_status": "waiting for memory processing",
                        "last_message": "Phase 1 complete — processing memories...",
                    }
                time.sleep(TEST_PHASE_MEMORY_DELAY_SECONDS)
                trigger_graph_rebuild_sync()
    else:
        # Normal: msg1 + msg2 in same session per player
        for npc_idx, npc_config in enumerate(npc_configs):
            if not test_state["running"]:
                break
            
            npc_id = npc_config["npc_id"]
            messages = [npc_config.get("message_1", ""), npc_config.get("message_2", "")]
            
            test_state["current_npc"] = npc_id
            test_state["phase"] = "normal"
            
            for i in range(1, num_players + 1):
                if not test_state["running"]:
                    break
                
                test_state["current_player"] = i
                
                player_id = f"{player_name_base}_{npc_id}_{str(i).zfill(3)}"
                player_name = f"{player_name_base} {i}"
                
                thread = threading.Thread(
                    target=run_player_session_thread,
                    args=(i, player_id, player_name, npc_id, messages)
                )
                thread.start()
                thread.join()
                
                if i < num_players and test_state["running"]:
                    time.sleep(TEST_PLAYER_DELAY_SECONDS)
            
            if npc_idx < len(npc_configs) - 1 and test_state["running"]:
                time.sleep(TEST_NPC_SWITCH_DELAY_SECONDS)
    
    trigger_graph_rebuild_sync()
    test_state["running"] = False
    test_state["phase"] = "complete"


@app.get("/test-10-player", response_class=HTMLResponse)
async def serve_test_page():
    """Serve the 10-player memory test page."""
    return HTMLResponse(HTML_TEST_PAGE)


@app.post("/api/start-test")
async def api_start_test(config: TestConfig):
    """Start the 10-player memory test."""
    global test_state
    
    if test_state["running"]:
        raise HTTPException(400, "Test already running")
    
    test_state = {
        "running": True,
        "config": config.model_dump(),
        "current_player": 0,
        "results": [],
        "start_time": int(time.time() * 1000),
        "last_update": None,
    }
    
    thread = threading.Thread(target=run_full_test_thread, args=(config.model_dump(),))
    thread.start()
    
    return {"status": "started", "num_players": config.num_players}


@app.post("/api/stop-test")
async def api_stop_test():
    """Stop the running test."""
    with _test_lock:
        test_state["running"] = False
    return {"status": "stopped"}


@app.get("/api/test-status")
async def api_test_status():
    """Get current test status."""
    with _test_lock:
        last_update = dict(test_state.get("last_update") or {})
        results_snapshot = [
            {
                "player_id": r["player_id"],
                "player_name": r["player_name"],
                "session_id": r["session_id"][:8] if r.get("session_id") else None,
                "session_status": r.get("session_status", r.get("last_message", "")),
                "turn_count": r["turn_count"],
                "memory_created": r["memory_created"],
                "memory_loaded_on_start": r.get("memory_loaded_on_start", False),
                "history_verified": r.get("history_verified", False),
                "player_memories_verified": r.get("player_memories_verified", False),
                "god_memory_verified": r.get("god_memory_verified", False),
                "identity_verified": r.get("identity_verified"),
                "error": r.get("error"),
                "duration_seconds": round(r["duration_seconds"], 1),
            }
            for r in test_state["results"]
        ]
    
    return {
        "running": test_state["running"],
        "config": test_state.get("config"),
        "phase": test_state.get("phase", "normal"),
        "cross_session": test_state.get("cross_session", False),
        "current_player": test_state["current_player"],
        "current_npc": test_state.get("current_npc"),
        "total_expected": test_state.get("total_expected", 0),
        "results": results_snapshot,
        "start_time": test_state.get("start_time"),
        "last_update": last_update,
    }


@app.get("/api/npc-identity-probe/{npc_id}")
async def api_npc_identity_probe(npc_id: str) -> dict:
    """Probe an NPC's identity with a character-specific question."""
    result = probe_npc_identity_sync(npc_id)
    if result is None:
        raise HTTPException(404, f"No probe configured for NPC '{npc_id}'")
    return result


@app.get("/api/all-npc-identity")
async def api_all_npc_identity() -> dict:
    """Probe all NPCs' identities at once."""
    results = {}
    for npc_id in ["ai_news_instructor", "maestro_jazz_instructor", "llm_instructor",
                   "marvel_comics_instructor", "supabase_instructor", "kosmos_instructor"]:
        results[npc_id] = probe_npc_identity_sync(npc_id) or {"npc_id": npc_id, "error": "probe failed"}
    return {"probes": results}


@app.get("/api/all-npc-lora")
async def api_all_npc_lora() -> dict:
    """Get LoRA status for all NPCs."""
    return get_all_npc_lora_status_sync()


@app.get("/api/gpu-status")
async def api_gpu_status() -> dict:
    """Get GPU acceleration status."""
    return get_gpu_acceleration_status()


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    if host in {"", "localhost", "0.0.0.0"} or not re.match(r"^[0-9.]+$", host):
        host = "127.0.0.1"
    port = int(os.environ.get("PORT", "8000"))
    print(f"Starting Uvicorn on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
