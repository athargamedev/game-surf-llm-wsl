#!/usr/bin/env python3
import json
import os
import sys
import xml.sax.saxutils as saxutils
from collections import defaultdict
from itertools import combinations
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "exports" / "dialogue_relation_graph"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


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


def get_env_values() -> tuple[str, str]:
    env = load_env_file(ROOT / ".env")
    supabase_url = os.environ.get("SUPABASE_URL") or env.get("SUPABASE_URL") or "http://127.0.0.1:16433"
    supabase_key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SERVICE_ROLE_KEY")
        or env.get("SUPABASE_SERVICE_ROLE_KEY")
        or env.get("SERVICE_ROLE_KEY")
        or ""
    ).strip()
    if not supabase_key:
        print("Error: SUPABASE_SERVICE_ROLE_KEY or SERVICE_ROLE_KEY must be set in environment or .env.")
        sys.exit(1)
    return supabase_url.rstrip("/"), supabase_key


def supabase_headers(supabase_key: str) -> dict[str, str]:
    return {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
    }


def fetch_relation_terms(base_url: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    resp = requests.get(
        f"{base_url}/rest/v1/dialogue_relation_terms?select=term,description",
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_relation_matches(base_url: str, headers: dict[str, str]) -> list[dict[str, Any]]:
    resp = requests.post(
        f"{base_url}/rest/v1/rpc/get_dialogue_relation_matches",
        headers=headers,
        json={},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def fetch_live_graph(base_url: str) -> dict[str, Any]:
    resp = requests.get(f"{base_url}/graph/view", timeout=30)
    resp.raise_for_status()
    return resp.json()


def make_graph(terms: list[dict[str, Any]], matches: list[dict[str, Any]]) -> dict[str, Any]:
    term_lookup = {str(term["term"]): term for term in terms}
    player_nodes: dict[str, dict[str, Any]] = {}
    term_nodes: dict[str, dict[str, Any]] = {}
    player_term_edges: dict[tuple[str, str], dict[str, Any]] = {}
    term_players: dict[str, set[str]] = defaultdict(set)

    for match in matches:
        term = str(match.get("term", "")).strip()
        player_id = str(match.get("player_id", "")).strip()
        if not term or not player_id:
            continue

        term_entry = term_lookup.get(term, {})
        term_id = f"term:{term}"
        player_id_key = f"player:{player_id}"

        term_nodes[term] = {
            "id": term_id,
            "label": term,
            "type": "term",
            "description": term_entry.get("description") or "",
        }
        player_nodes[player_id] = {
            "id": player_id_key,
            "label": player_id,
            "type": "player",
        }

        edge_key = (player_id, term)
        edge = player_term_edges.setdefault(
            edge_key,
            {
                "source": player_id_key,
                "target": term_id,
                "type": "uses",
                "weight": 0,
                "message_count": 0,
                "messages": [],
            },
        )
        edge["weight"] += 1
        edge["messages"].append({
            "source": match.get("source"),
            "session_id": match.get("session_id"),
            "message": match.get("message"),
            "matched_at": match.get("matched_at"),
        })
        edge["message_count"] = len(edge["messages"])
        term_players[term].add(player_id)

    shared_edges: dict[tuple[str, str], dict[str, Any]] = {}
    for term, players in term_players.items():
        sorted_players = sorted(players)
        for a, b in combinations(sorted_players, 2):
            edge_key = (a, b)
            shared = shared_edges.setdefault(
                edge_key,
                {
                    "source": f"player:{a}",
                    "target": f"player:{b}",
                    "type": "shared_term",
                    "terms": [],
                    "weight": 0,
                },
            )
            shared["terms"].append(term)
            shared["weight"] += 1

    graph = {
        "nodes": list(player_nodes.values()) + list(term_nodes.values()),
        "edges": list(player_term_edges.values()) + list(shared_edges.values()),
        "summary": {
            "player_count": len(player_nodes),
            "term_count": len(term_nodes),
            "edge_count": len(player_term_edges) + len(shared_edges),
            "match_count": len(matches),
        },
    }
    return graph


def write_json(graph: dict[str, Any]) -> None:
    output_path = OUTPUT_DIR / "graph.json"
    output_path.write_text(json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote JSON graph to: {output_path}")


def write_xml(graph: dict[str, Any]) -> None:
    lines = ["<relationGraph>"]
    lines.append("  <summary>")
    for key, value in graph["summary"].items():
        lines.append(f"    <{key}>{value}</{key}>")
    lines.append("  </summary>")
    lines.append("  <nodes>")
    for node in graph["nodes"]:
        lines.append(f"    <node id=\"{node['id']}\" label=\"{node['label']}\" type=\"{node['type']}\">")
        if node.get("description"):
            lines.append(f"      <description>{node['description']}</description>")
        lines.append("    </node>")
    lines.append("  </nodes>")
    lines.append("  <edges>")
    for edge in graph["edges"]:
        attrs = [f"type=\"{edge['type']}\"", f"source=\"{edge['source']}\"", f"target=\"{edge['target']}\"", f"weight=\"{edge.get('weight', 0)}\""]
        if edge.get("terms"):
            attrs.append(f"terms=\"{','.join(edge['terms'])}\"")
        lines.append(f"    <edge {' '.join(attrs)}>")
        if edge.get("message_count") is not None:
            lines.append(f"      <message_count>{edge['message_count']}</message_count>")
        if edge.get("messages"):
            lines.append("      <messages>")
            for msg in edge["messages"]:
                lines.append("        <message>")
                for mkey in ["source", "session_id", "matched_at"]:
                    if msg.get(mkey) is not None:
                        lines.append(f"          <{mkey}>{saxutils.escape(str(msg[mkey]))}</{mkey}>")
                lines.append(f"          <text>{saxutils.escape(str(msg.get('message', '')))}</text>")
                lines.append("        </message>")
            lines.append("      </messages>")
        lines.append("    </edge>")
    lines.append("  </edges>")
    lines.append("</relationGraph>")

    output_path = OUTPUT_DIR / "graph.xml"
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote XML graph to: {output_path}")


def main() -> None:
    supabase_url, supabase_key = get_env_values()
    headers = supabase_headers(supabase_key)

    try:
        live_graph = fetch_live_graph(supabase_url)
        graph = {
            "nodes": live_graph.get("nodes", []),
            "edges": live_graph.get("edges", []),
            "summary": {
                "player_count": len([node for node in live_graph.get("nodes", []) if str(node.get("node_type") or node.get("type")) == "player"]),
                "term_count": len([node for node in live_graph.get("nodes", []) if str(node.get("node_type") or node.get("type")) == "term"]),
                "edge_count": len(live_graph.get("edges", [])),
                "match_count": sum(
                    int(edge.get("metadata", {}).get("message_count", 0) or 0)
                    for edge in live_graph.get("edges", [])
                ),
            },
        }
    except Exception:
        terms = fetch_relation_terms(supabase_url, headers)
        matches = fetch_relation_matches(supabase_url, headers)
        graph = make_graph(terms, matches)

    write_json(graph)
    write_xml(graph)
    print(f"Generated graph with {graph['summary']['player_count']} players and {graph['summary']['term_count']} terms.")


if __name__ == "__main__":
    main()
