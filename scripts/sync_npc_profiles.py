#!/usr/bin/env python3
"""
Sync NPC profiles from JSON config to Supabase database.
Creates/updates npc_profiles table entries.
"""

import json
import sys
from pathlib import Path
from supabase_client import get_client, NPCProfile

ROOT = Path(__file__).resolve().parent.parent
NPC_PROFILES_JSON = ROOT / "datasets" / "configs" / "npc_profiles.json"


def load_npc_profiles_from_json() -> list[dict]:
    if not NPC_PROFILES_JSON.exists():
        print(f"NPC profiles file not found: {NPC_PROFILES_JSON}")
        sys.exit(1)
    
    data = json.loads(NPC_PROFILES_JSON.read_text(encoding="utf-8"))
    return list(data.get("profiles", {}).items())


def sync_npcs() -> int:
    client = get_client()
    if client.get_instance() is None:
        print("Not connected to Supabase")
        sys.exit(1)
    
    profiles_data = load_npc_profiles_from_json()
    synced = 0
    
    for npc_id, profile in profiles_data:
        npc = NPCProfile(
            npc_id=npc_id,
            display_name=profile.get("display_name", ""),
            npc_scope=profile.get("npc_scope", "instructor"),
            subject=profile.get("subject"),
            subject_focus=profile.get("subject_focus"),
            personality=profile.get("personality", {}),
            voice_rules=profile.get("voice_rules", []),
            is_active=True,
        )
        
        if client.upsert_npc_profile(npc):
            print(f"  Synced: {npc_id} -> {npc.display_name}")
            synced += 1
        else:
            print(f"  Failed: {npc_id}")
    
    return synced


def main() -> None:
    print("NPC Profile Sync")
    print("=" * 50)
    print(f"Source: {NPC_PROFILES_JSON}")
    print("")
    
    count = sync_npcs()
    print("")
    print(f"Synced {count} NPC profiles to database")


if __name__ == "__main__":
    main()