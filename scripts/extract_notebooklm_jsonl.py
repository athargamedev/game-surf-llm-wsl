#!/usr/bin/env python3
"""Extract JSONL from NotebookLM ask --json output."""
import sys, json

raw = sys.stdin.read()

# Extract answer field from JSON response
try:
    resp = json.loads(raw)
    if isinstance(resp, dict) and "answer" in resp:
        text = resp["answer"]
    else:
        text = raw
except (json.JSONDecodeError, ValueError):
    text = raw

# NotebookLM returns \n-separated JSON objects in the answer
objects = []
for line in text.strip().split("\n"):
    line = line.strip()
    if not line:
        continue
    try:
        parsed = json.loads(line)
        objects.append(json.dumps(parsed, ensure_ascii=False))
    except (json.JSONDecodeError, ValueError):
        pass

output_file = sys.argv[1] if len(sys.argv) > 1 else None
print(f"Found {len(objects)} JSON objects")
if objects and output_file:
    with open(output_file, "w") as f:
        f.write("\n".join(objects) + "\n")
    print(f"Written: {output_file}")
elif objects:
    for obj in objects[:3]:
        d = json.loads(obj)
        msgs = d.get("messages", [])
        user = next((m["content"][:100] for m in msgs if m.get("role") == "user"), "?")
        asst = next((m["content"][:100] for m in msgs if m.get("role") == "assistant"), "?")
        meta = d.get("metadata", {})
        print(f"Role: {meta.get('npc_key')} | Type: {meta.get('task_type')}")
        print(f"User: {user}")
        print(f"Asst: {asst}")
        print("---")