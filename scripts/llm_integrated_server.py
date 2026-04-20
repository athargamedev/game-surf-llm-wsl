#!/usr/bin/env python
"""Integrated Game_Surf LLM server with relay, Supabase memory, and reload endpoints."""

from __future__ import annotations

from dataclasses import dataclass, field
import asyncio
import json
import os
import re
import uuid
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from llama_index.core import StorageContext, SimpleDirectoryReader, Settings, VectorStoreIndex, load_index_from_storage
from llama_index.core.base.llms.types import ChatMessage, MessageRole
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.llama_cpp import LlamaCPP
from llama_index.core.memory import ChatMemoryBuffer
from supabase import Client, create_client
from scripts.supabase_client import SupabaseClient, get_client as get_supabase

app = FastAPI(title="Game_Surf NPC Dialogue Integrated Server")

# Enable CORS for browser requests from localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8080", "http://localhost:8080", "http://127.0.0.1", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
DIRECT_CHAT_MAX_TURNS = int(os.environ.get("DIRECT_CHAT_MAX_TURNS", "6"))
GRAPH_REFRESH_INTERVAL_SECONDS = int(os.environ.get("GRAPH_REFRESH_INTERVAL_SECONDS", "1800"))
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
    # Note: Don't add <|begin_of_text|> here - llama.cpp chat template adds it automatically
    # Adding it twice causes the "Detected duplicate" warning
    prompt_parts = []
    for message in messages:
        role = message.role.value if hasattr(message.role, "value") else str(message.role)
        content = str(message.content).strip()
        prompt_parts.append(
            f"<|start_header_id|>{role}<|end_header_id|>\n\n{content}<|eot_id|>"
        )
    prompt_parts.append("<|start_header_id|>assistant<|end_header_id|>\n\n")
    return "".join(prompt_parts)


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
    for pattern in RESPONSE_CUTOFF_PATTERNS:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            cleaned = cleaned[: match.start()].strip()
            break

    cleaned = re.sub(r"^\s*assistant\s*[:\-]?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+\Z", "", cleaned)
    return cleaned.strip()


def extract_chat_text(response) -> str:
    message = getattr(response, "message", None)
    content = getattr(message, "content", None)
    if content:
        return str(content)
    return str(response)


def build_system_prompt(npc_id: str) -> str:
    system_prompt = f"You are a helpful NPC inside Game_Surf. {MEMORY_SLOT}"
    try:
        profiles_path = TOOLS_LLM_ROOT / "datasets" / "configs" / "npc_profiles.json"
        if profiles_path.exists():
            profiles_data = json.loads(profiles_path.read_text(encoding="utf-8"))
            profiles = profiles_data.get("profiles", {})
            prof = profiles.get(npc_id)
            if not prof:
                for key, value in profiles.items():
                    if npc_id in key or key in npc_id:
                        prof = value
                        break
            if prof:
                voice_rules = prof.get("voice_rules", [])
                voice_rules_text = " ".join(f"- {rule}" for rule in voice_rules[:6])
                system_prompt = (
                    f"You are {prof.get('display_name', npc_id)}, an NPC inside Game_Surf. "
                    f"{MEMORY_SLOT} "
                    f"You focus on {prof.get('subject', '')}. "
                    f"Tone: {prof.get('personality', {}).get('tone', '')}. "
                    f"Speaking style: {prof.get('personality', {}).get('speaking_style', '')}. "
                    f"Rules: {voice_rules_text} "
                    "Reply as this NPC only. "
                    "Do not write role labels, transcripts, stage directions, scene descriptions, or multiple turns. "
                    "Give one direct reply to the player's latest message."
                )
    except Exception as exc:
        print(f"Warn: failed to build system prompt for {npc_id}: {exc}")
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
        model_kwargs = {}
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
    if npc_adapter_is_active(npc_id):
        session = DirectNpcChatSession(system_prompt=system_prompt)
        chat_engines[key] = session
        return session

    index = load_index()
    if index is None:
        raise RuntimeError("Failed to load retrieval index")

    engine = index.as_chat_engine(
        chat_mode="context",
        memory=ChatMemoryBuffer.from_defaults(token_limit=CHAT_HISTORY_TOKEN_LIMIT),
        system_prompt=system_prompt,
    )

    chat_engines[key] = engine
    return engine


@app.on_event("startup")
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
    )


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    select_npc_runtime(request.npc_id)
    if Settings.llm is None:
        raise HTTPException(status_code=500, detail="NPC Brain model is not loaded.")

    try:
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

        return ChatResponse(npc_response=npc_text, session_id=session_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """Stream NPC response tokens in real-time using Server-Sent Events (SSE)."""
    select_npc_runtime(request.npc_id)
    if Settings.llm is None:
        raise HTTPException(status_code=500, detail="NPC Brain model is not loaded.")

    async def generate():
        try:
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
                print(f"[MEMORY] Ending stale active session {old_session_id} for {request.player_id}/{request.npc_id}")
                supabase_client.table("dialogue_sessions").update(
                    {"status": "ended", "ended_at": "now()"}
                ).eq("session_id", old_session_id).execute()
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
    """Select the shared base model plus optional NPC LoRA adapter."""
    global MODEL_PATH, active_npc_id, active_lora_adapter_path

    load_npc_model_registry()

    selected_npc = npc_id.strip() if npc_id else None
    selected_model_path = normalize_manifest_path(model_path) if model_path else BASE_MODEL_PATH
    selected_lora_path: str | None = None

    if selected_npc:
        selected_lora_path = resolve_lora_adapter_path_for_npc(selected_npc)
        dedicated_gguf = resolve_gguf_model_path_for_npc(selected_npc)
        if selected_lora_path:
            selected_model_path = BASE_MODEL_PATH
        elif dedicated_gguf:
            selected_model_path = dedicated_gguf
        elif selected_npc not in npc_model_registry:
            print(f"No trained adapter manifest found for NPC '{selected_npc}'. Using base model.")

    if not selected_model_path:
        selected_model_path = BASE_MODEL_PATH

    normalized_model = normalize_manifest_path(selected_model_path) or selected_model_path
    changed = (
        Path(normalized_model).resolve() != Path(normalize_manifest_path(MODEL_PATH) or MODEL_PATH).resolve()
        or selected_lora_path != active_lora_adapter_path
        or selected_npc != active_npc_id
    )

    if changed:
        MODEL_PATH = normalized_model
        active_npc_id = selected_npc
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


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")
