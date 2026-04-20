#!/usr/bin/env python3
"""
Game_Surf Supabase Client - Centralized typed client for database operations.
Provides session management, memory operations, and NPC profile access.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
import uuid
from supabase import Client, create_client

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


def get_config() -> tuple[str, str, bool]:
    env = load_env_file(ROOT / ".env")
    url = os.environ.get("SUPABASE_URL") or env.get("SUPABASE_URL", "http://127.0.0.1:16433")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_SERVICE_ROLE_KEY", "")
    enabled = os.environ.get("ENABLE_SUPABASE", "true").lower() == "true"
    return url, key, enabled


@dataclass
class PlayerProfile:
    player_id: str
    display_name: str
    created_at: datetime
    updated_at: datetime


@dataclass
class NPCProfile:
    npc_id: str
    display_name: str
    npc_scope: str
    subject: Optional[str] = None
    subject_focus: Optional[str] = None
    personality: dict = field(default_factory=dict)
    voice_rules: list = field(default_factory=list)
    is_active: bool = True


@dataclass
class DialogueSession:
    session_id: uuid.UUID
    player_id: str
    npc_id: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime] = None


@dataclass
class DialogueTurn:
    turn_id: int
    session_id: uuid.UUID
    player_message: str
    npc_response: str
    created_at: datetime


@dataclass
class NPCMemory:
    memory_id: int
    player_id: str
    npc_id: str
    summary: str
    created_at: datetime
    raw_json: dict = field(default_factory=dict)


class SupabaseClient:
    _instance: Optional[Client] = None
    _url: str = ""
    _key: str = ""
    _enabled: bool = False

    def __init__(self) -> None:
        pass

    @classmethod
    def get_instance(cls) -> Optional[Client]:
        if cls._instance is not None:
            return cls._instance
        if not cls._enabled or not cls._key:
            return None
        try:
            cls._instance = create_client(cls._url, cls._key)
            return cls._instance
        except Exception as e:
            print(f"Supabase connection failed: {e}")
            return None

    @classmethod
    def initialize(cls) -> bool:
        cls._url, cls._key, cls._enabled = get_config()
        if not cls._enabled:
            print("Supabase disabled")
            return False
        if not cls._key:
            print("Supabase skipped: SERVICE_ROLE_KEY not configured")
            return False
        client = cls.get_instance()
        if client is None:
            return False
        print(f"Connected to Supabase at {cls._url}")
        return True

    def get_player_profile(self, player_id: str) -> Optional[PlayerProfile]:
        client = self.get_instance()
        if client is None:
            return None
        resp = client.table("player_profiles").select("*").eq("player_id", player_id).limit(1).execute()
        if not resp.data:
            return None
        data = resp.data[0]
        return PlayerProfile(
            player_id=data["player_id"],
            display_name=data["display_name"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )

    def upsert_player_profile(self, player_id: str, display_name: str) -> bool:
        client = self.get_instance()
        if client is None:
            return False
        try:
            client.table("player_profiles").upsert({
                "player_id": player_id,
                "display_name": display_name,
            }).execute()
            return True
        except Exception as e:
            print(f"Player profile upsert failed: {e}")
            return False

    def get_npc_profile(self, npc_id: str) -> Optional[NPCProfile]:
        client = self.get_instance()
        if client is None:
            return None
        try:
            resp = client.rpc("get_npc_profile", {"target_npc_id": npc_id}).execute()
            if not resp.data:
                return None
            data = resp.data[0]
            return NPCProfile(
                npc_id=data["npc_id"],
                display_name=data["display_name"],
                npc_scope=data["npc_scope"],
                subject=data.get("subject"),
                personality=data.get("personality", {}),
                voice_rules=data.get("voice_rules", []),
            )
        except Exception as e:
            print(f"get_npc_profile failed: {e}")
            return None

    def list_active_npcs(self) -> list[NPCProfile]:
        client = self.get_instance()
        if client is None:
            return []
        resp = client.table("npc_profiles").select("*").eq("is_active", True).execute()
        return [
            NPCProfile(
                npc_id=row["npc_id"],
                display_name=row["display_name"],
                npc_scope=row["npc_scope"],
                subject=row.get("subject"),
                subject_focus=row.get("subject_focus"),
                personality=row.get("personality", {}),
                voice_rules=row.get("voice_rules", []),
            )
            for row in resp.data or []
        ]

    def upsert_npc_profile(self, profile: NPCProfile) -> bool:
        client = self.get_instance()
        if client is None:
            return False
        try:
            client.rpc("upsert_npc_profile", {
                "p_npc_id": profile.npc_id,
                "p_display_name": profile.display_name,
                "p_npc_scope": profile.npc_scope,
                "p_artifact_key": None,
                "p_subject": profile.subject,
                "p_subject_focus": profile.subject_focus,
                "p_personality": profile.personality,
                "p_voice_rules": profile.voice_rules,
                "p_domain_knowledge": [],
            }).execute()
            return True
        except Exception as e:
            print(f"upsert_npc_profile failed: {e}")
            return False

    def create_session(self, player_id: str, npc_id: str) -> Optional[uuid.UUID]:
        client = self.get_instance()
        if client is None:
            return None
        try:
            resp = client.table("dialogue_sessions").insert({
                "player_id": player_id,
                "npc_id": npc_id,
                "status": "active",
            }).execute()
            if resp.data:
                return uuid.UUID(resp.data[0]["session_id"])
            return None
        except Exception as e:
            print(f"Create session failed: {e}")
            return None

    def end_session(self, session_id: uuid.UUID) -> bool:
        client = self.get_instance()
        if client is None:
            return False
        try:
            client.table("dialogue_sessions").update({
                "status": "ended",
                "ended_at": "now()",
            }).eq("session_id", str(session_id)).execute()
            return True
        except Exception as e:
            print(f"End session failed: {e}")
            return False

    def get_active_session(self, player_id: str, npc_id: str) -> Optional[uuid.UUID]:
        client = self.get_instance()
        if client is None:
            return None
        resp = (
            client.table("dialogue_sessions")
            .select("session_id")
            .eq("player_id", player_id)
            .eq("npc_id", npc_id)
            .eq("status", "active")
            .limit(1)
            .execute()
        )
        if resp.data:
            return uuid.UUID(resp.data[0]["session_id"])
        return None

    def record_turn(self, session_id: uuid.UUID, player_message: str, npc_response: str) -> Optional[int]:
        client = self.get_instance()
        if client is None:
            return None
        try:
            resp = client.table("dialogue_turns").insert({
                "session_id": str(session_id),
                "player_message": player_message,
                "npc_response": npc_response,
                "raw_json": {"user": player_message, "npc": npc_response},
            }).execute()
            if resp.data:
                return resp.data[0]["turn_id"]
            return None
        except Exception as e:
            print(f"Record turn failed: {e}")
            return None

    def get_session_turns(self, session_id: uuid.UUID) -> list[DialogueTurn]:
        client = self.get_instance()
        if client is None:
            return []
        resp = (
            client.table("dialogue_turns")
            .select("*")
            .eq("session_id", str(session_id))
            .order("created_at")
            .execute()
        )
        return [
            DialogueTurn(
                turn_id=row["turn_id"],
                session_id=uuid.UUID(row["session_id"]),
                player_message=row["player_message"],
                npc_response=row["npc_response"],
                created_at=row["created_at"],
            )
            for row in resp.data or []
        ]

    def get_memories(self, player_id: str, npc_id: str, limit: int = 5) -> list[NPCMemory]:
        client = self.get_instance()
        if client is None:
            return []
        resp = (
            client.table("npc_memories")
            .select("*")
            .eq("player_id", player_id)
            .eq("npc_id", npc_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [
            NPCMemory(
                memory_id=row["memory_id"],
                player_id=row["player_id"],
                npc_id=row["npc_id"],
                summary=row["summary"],
                created_at=row["created_at"],
                raw_json=row.get("raw_json", {}),
            )
            for row in resp.data or []
        ]

    def get_latest_memory(self, player_id: str, npc_id: str) -> Optional[NPCMemory]:
        memories = self.get_memories(player_id, npc_id, limit=1)
        return memories[0] if memories else None

    def create_memory(self, player_id: str, npc_id: str, summary: str, raw_json: Optional[dict] = None) -> Optional[int]:
        client = self.get_instance()
        if client is None:
            return None
        try:
            resp = client.table("npc_memories").insert({
                "player_id": player_id,
                "npc_id": npc_id,
                "summary": summary,
                "raw_json": raw_json or {},
            }).execute()
            if resp.data:
                return resp.data[0]["memory_id"]
            return None
        except Exception as e:
            print(f"Create memory failed: {e}")
            return None

    def get_player_npc_stats(self, player_id: str, npc_id: str) -> dict[str, Any]:
        client = self.get_instance()
        if client is None:
            return {}
        try:
            resp = client.rpc("get_player_npc_stats", {
                "target_player_id": player_id,
                "target_npc_id": npc_id,
            }).execute()
            if resp.data:
                return resp.data[0]
            return {}
        except Exception as e:
            print(f"Get stats failed: {e}")
            return {}

    def load_player_context(self, player_id: str, npc_id: str) -> str:
        parts: list[str] = []
        
        if profile := self.get_player_profile(player_id):
            parts.append(f"Player: {profile.display_name}")

        memories = self.get_memories(player_id, npc_id, limit=3)
        if memories:
            mem_lines = []
            for idx, mem in enumerate(memories, start=1):
                summary = mem.summary[:200].replace("\n", " ")
                mem_lines.append(f"{idx}. {summary}")
            parts.append("Memories:\n" + "\n".join(mem_lines))

        if npc := self.get_npc_profile(npc_id):
            parts.append(f"NPC: {npc.display_name} - {npc.subject or 'General'}")

        return "\n\n".join(parts) if parts else "No context available."


_client: Optional[SupabaseClient] = None


def get_client() -> SupabaseClient:
    global _client
    if _client is None:
        _client = SupabaseClient()
        _client.initialize()
    return _client


def main() -> None:
    print("Game_Surf Supabase Client")
    print("=" * 50)
    
    client = get_client()
    if client.get_instance() is None:
        print("Not connected to Supabase")
        return

    print("\nActive NPCs:")
    for npc in client.list_active_npcs():
        print(f"  - {npc.npc_id}: {npc.display_name}")

    print("\nStats for test player/test_npc:")
    stats = client.get_player_npc_stats("test_player", "kosmos_instructor")
    if stats:
        print(f"  Sessions: {stats.get('total_sessions')}, Turns: {stats.get('total_turns')}, Memories: {stats.get('total_memories')}")
    else:
        print("  No data")


if __name__ == "__main__":
    main()