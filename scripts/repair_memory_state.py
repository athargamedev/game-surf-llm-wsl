#!/usr/bin/env python
"""Diagnose and optionally repair Supabase dialogue-memory bookkeeping."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


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


def parse_env_output(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def discover_db_url(explicit_url: str | None) -> str:
    if explicit_url:
        return explicit_url
    if os.environ.get("DATABASE_URL"):
        return str(os.environ["DATABASE_URL"])
    if os.environ.get("DB_URL"):
        return str(os.environ["DB_URL"])
    env_file = load_env_file(ROOT / ".env")
    if env_file.get("DATABASE_URL"):
        return env_file["DATABASE_URL"]
    if env_file.get("DB_URL"):
        return env_file["DB_URL"]

    result = subprocess.run(
        ["supabase", "status", "-o", "env"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    values = parse_env_output(result.stdout)
    if values.get("DB_URL"):
        return values["DB_URL"]
    config_url = discover_db_url_from_supabase_config(ROOT / "supabase" / "config.toml")
    if config_url:
        return config_url
    raise RuntimeError("Could not discover DATABASE_URL/DB_URL. Is local Supabase running?")


def discover_db_url_from_supabase_config(path: Path) -> str | None:
    if not path.exists():
        return None
    in_db_section = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("[") and line.endswith("]"):
            in_db_section = line == "[db]"
            continue
        if in_db_section and line.startswith("port") and "=" in line:
            _, value = line.split("=", 1)
            port = value.strip().strip('"').strip("'")
            if port.isdigit():
                return f"postgresql://postgres:postgres@127.0.0.1:{port}/postgres"
    return None


def psql(db_url: str, sql: str) -> str:
    result = subprocess.run(
        ["psql", db_url, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-At", "-F", "\t", "-c", sql],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stdout.strip())
    return result.stdout.strip()


def scalar_int(db_url: str, sql: str) -> int:
    text = psql(db_url, sql)
    return int(text.splitlines()[0]) if text else 0


def table_exists(db_url: str, table_name: str) -> bool:
    return scalar_int(
        db_url,
        f"""
        select count(*)
        from information_schema.tables
        where table_schema = 'public'
          and table_name = '{table_name}';
        """,
    ) > 0


def column_exists(db_url: str, table_name: str, column_name: str) -> bool:
    return scalar_int(
        db_url,
        f"""
        select count(*)
        from information_schema.columns
        where table_schema = 'public'
          and table_name = '{table_name}'
          and column_name = '{column_name}';
        """,
    ) > 0


def query_report(db_url: str, stale_hours: int) -> dict[str, Any]:
    if not table_exists(db_url, "dialogue_sessions"):
        return {"error": "dialogue_sessions table not found"}

    has_turn_count = column_exists(db_url, "dialogue_sessions", "turn_count")
    report: dict[str, Any] = {
        "has_turn_count": has_turn_count,
        "session_status_counts": {},
        "stale_turn_count_rows": None,
        "active_sessions_older_than_hours": stale_hours,
        "stale_active_sessions": 0,
        "orphan_memory_rows": 0,
        "untagged_recall_probe_memories": 0,
    }

    status_rows = psql(
        db_url,
        """
        select coalesce(status, '<null>'), count(*)
        from public.dialogue_sessions
        group by coalesce(status, '<null>')
        order by 1;
        """,
    )
    for line in status_rows.splitlines():
        if not line:
            continue
        status, count_text = line.split("\t", 1)
        report["session_status_counts"][status] = int(count_text)

    if has_turn_count:
        report["stale_turn_count_rows"] = scalar_int(
            db_url,
            """
            with actuals as (
                select ds.session_id, coalesce(count(dt.turn_id), 0)::integer as actual_turns
                from public.dialogue_sessions ds
                left join public.dialogue_turns dt on dt.session_id = ds.session_id
                group by ds.session_id
            )
            select count(*)
            from public.dialogue_sessions ds
            join actuals a on a.session_id = ds.session_id
            where coalesce(ds.turn_count, 0) <> a.actual_turns;
            """,
        )

    report["stale_active_sessions"] = scalar_int(
        db_url,
        f"""
        select count(*)
        from public.dialogue_sessions
        where status = 'active'
          and started_at < now() - interval '{int(stale_hours)} hours';
        """,
    )

    if table_exists(db_url, "npc_memories"):
        report["orphan_memory_rows"] = scalar_int(
            db_url,
            """
            select count(*)
            from public.npc_memories m
            left join public.dialogue_sessions ds on (
                (m.raw_json->>'session_id') ~* '^[0-9a-f-]{36}$'
                and ds.session_id = (m.raw_json->>'session_id')::uuid
            )
            where (m.raw_json->>'session_id') ~* '^[0-9a-f-]{36}$'
              and ds.session_id is null;
            """,
        )
        report["untagged_recall_probe_memories"] = scalar_int(
            db_url,
            """
            select count(*)
            from public.npc_memories
            where coalesce(raw_json->>'memory_kind', '') = ''
              and (
                lower(summary) like '%do you remember%'
                or lower(summary) like '%last conversation%'
                or lower(summary) like '%past session%'
                or lower(summary) like '%our previous conversation%'
              );
            """,
        )
    return report


def apply_repairs(db_url: str, stale_hours: int, end_stale_active: bool) -> dict[str, int]:
    applied = {
        "turn_count_rows_updated": 0,
        "recall_probe_memories_tagged": 0,
        "stale_active_sessions_ended": 0,
    }
    if column_exists(db_url, "dialogue_sessions", "turn_count"):
        updated = psql(
            db_url,
            """
            with actuals as (
                select ds.session_id, coalesce(count(dt.turn_id), 0)::integer as actual_turns
                from public.dialogue_sessions ds
                left join public.dialogue_turns dt on dt.session_id = ds.session_id
                group by ds.session_id
            ),
            updated as (
                update public.dialogue_sessions ds
                set turn_count = a.actual_turns
                from actuals a
                where ds.session_id = a.session_id
                  and coalesce(ds.turn_count, 0) <> a.actual_turns
                returning ds.session_id
            )
            select count(*) from updated;
            """,
        )
        applied["turn_count_rows_updated"] = int(updated or "0")

    if table_exists(db_url, "npc_memories"):
        tagged = psql(
            db_url,
            """
            with tagged as (
                update public.npc_memories
                set raw_json = raw_json || jsonb_build_object('memory_kind', 'recall_probe')
                where coalesce(raw_json->>'memory_kind', '') = ''
                  and (
                    lower(summary) like '%do you remember%'
                    or lower(summary) like '%last conversation%'
                    or lower(summary) like '%past session%'
                    or lower(summary) like '%our previous conversation%'
                  )
                returning memory_id
            )
            select count(*) from tagged;
            """,
        )
        applied["recall_probe_memories_tagged"] = int(tagged or "0")

    if end_stale_active:
        ended = psql(
            db_url,
            f"""
            with ended as (
                update public.dialogue_sessions
                set status = 'ended',
                    ended_at = coalesce(ended_at, now()),
                    raw_json = raw_json || jsonb_build_object('ended_by', 'repair_memory_state')
                where status = 'active'
                  and started_at < now() - interval '{int(stale_hours)} hours'
                returning session_id
            )
            select count(*) from ended;
            """,
        )
        applied["stale_active_sessions_ended"] = int(ended or "0")
    return applied


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-url", default=None, help="Postgres URL. Defaults to env or supabase status.")
    parser.add_argument("--stale-hours", type=int, default=12, help="Age threshold for active-session diagnostics.")
    parser.add_argument("--apply", action="store_true", help="Apply non-destructive metadata repairs.")
    parser.add_argument(
        "--end-stale-active",
        action="store_true",
        help="With --apply, mark stale active sessions ended. This can trigger memory summarization.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_url = discover_db_url(args.db_url)
    before = query_report(db_url, args.stale_hours)
    applied = apply_repairs(db_url, args.stale_hours, args.end_stale_active) if args.apply else {}
    after = query_report(db_url, args.stale_hours) if args.apply else None
    payload = {
        "database": db_url.split("@")[-1],
        "dry_run": not args.apply,
        "before": before,
        "applied": applied,
        "after": after,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"Database: {payload['database']}")
        print(f"Dry run: {payload['dry_run']}")
        print("Before:")
        print(json.dumps(before, indent=2, sort_keys=True))
        if args.apply:
            print("Applied:")
            print(json.dumps(applied, indent=2, sort_keys=True))
            print("After:")
            print(json.dumps(after, indent=2, sort_keys=True))
        else:
            print("No repairs applied. Re-run with --apply to update turn_count and tag recall probes.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"repair_memory_state failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
