#!/usr/bin/env python3
"""Extract JSONL from NotebookLM ask --json output."""
import sys, json, re

text = sys.stdin.read()
try:
    payload = json.loads(text)
    if isinstance(payload, dict) and "answer" in payload:
        text = payload["answer"]
except (json.JSONDecodeError, ValueError):
    pass

fence = re.search(r"```(?:jsonl|json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
if fence:
    text = fence.group(1).strip()
elif "Answer:" in text:
    text = text.split("Answer:", maxsplit=1)[1]

objects = []
current = []
depth = 0
in_str = False
esc = False
for c in text:
    if depth == 0:
        if c != "{":
            continue
        current = ["{"]
        depth = 1
        in_str = False
        esc = False
        continue
    if c in "\r\n":
        current.append(" ")
        esc = False
        continue
    current.append(c)
    if esc:
        esc = False
        continue
    if c == "\\" and in_str:
        esc = True
        continue
    if c == '"':
        in_str = not in_str
        continue
    if in_str:
        continue
    if c == "{":
        depth += 1
    elif c == "}":
        depth -= 1
        if depth == 0:
            try:
                parsed = json.loads("".join(current))
                objects.append(json.dumps(parsed))
            except (json.JSONDecodeError, ValueError):
                pass
            current = []

output_file = sys.argv[1] if len(sys.argv) > 1 else None
print(f"Found {len(objects)} JSON objects")
if objects and output_file:
    with open(output_file, "w") as f:
        f.write("\n".join(objects) + "\n")
    print(f"Written: {output_file}")
elif objects:
    for obj in objects[:2]:
        print(json.dumps(json.loads(obj), indent=2)[:300])
        print("---")