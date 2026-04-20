#!/usr/bin/env python
import argparse
import json
import time
import sys
import urllib.request
import urllib.error
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[4]
LLM_TOOLS_DIR = ROOT_DIR
PROFILES_PATH = LLM_TOOLS_DIR / "datasets" / "configs" / "npc_profiles.json"
LM_API_BASE = "http://127.0.0.1:1234/api/v1"

# LM Studio REST Management

def _make_lm_api_req(endpoint, method="GET", data=None):
    url = f"{LM_API_BASE}{endpoint}"
    headers = {}
    req_data = None
    if data:
        req_data = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as e:
        status = getattr(e, "code", "Connection Error")
        body = getattr(e, "read", lambda: b"")()
        try:
            body = body.decode("utf-8")
        except Exception:
            body = str(body)
        reason = getattr(e, "reason", e)
        print(f"[ERROR] API request failed: {status} {reason}")
        if body:
            print(f"Details: {body}")
        
        # If it is a 404, suggest they are running an older LM Studio.
        if status == 404:
            print("\n[HINT] Ensure you are running LM Studio 0.4.0+ with the v1 native REST API enabled.")
        sys.exit(1)

def lm_list():
    """List loaded models and available files."""
    print(f"Fetching models from {LM_API_BASE}/models ...")
    res = _make_lm_api_req("/models", method="GET")
    data = res.get("data", [])
    if not data:
        print("No models currently loaded.")
        return
        
    print("\nModels Currently Loaded/Available:")
    for m in data:
        m_id = m.get("id", "Unknown")
        print(f" - {m_id}")

def lm_load(model_id):
    """Load a model into memory by its identifier."""
    print(f"Loading model '{model_id}' into memory...")
    res = _make_lm_api_req("/models/load", method="POST", data={"model": model_id})
    print(f"[SUCCESS] Model loaded successfully! Instance details:\n{json.dumps(res, indent=2)}")

def lm_unload(identifier):
    """Unload a model from memory using its model ID or instance_id."""
    print(f"Unloading model '{identifier}'...")
    res = _make_lm_api_req("/models/unload", method="POST", data={"model": identifier})
    print(f"[SUCCESS] Server response:\n{json.dumps(res, indent=2)}")

def lm_download(model_id):
    """Initiate a model download from HuggingFace."""
    print(f"Initiating download for '{model_id}'...")
    res = _make_lm_api_req("/models/download", method="POST", data={"model": model_id})
    print(f"[SUCCESS] Download request sent. Server response:\n{json.dumps(res, indent=2)}")

# NPC Pipeline Tuning

def test_connection(base_url="http://127.0.0.1:1234/v1", model_id="local-model"):
    try:
        from openai import OpenAI
    except ImportError:
        print("Error: openai package is required for test-connection. Run: pip install openai")
        sys.exit(1)

    print(f"Testing generation latency on {base_url} with model '{model_id}'...")
    client = OpenAI(base_url=base_url, api_key="dummy")
    
    try:
        start = time.time()
        print("Sending lightweight sync request...")
        resp = client.chat.completions.create(
            model=model_id,
            messages=[{"role": "user", "content": "Reply with precisely one word: 'Ready'."}],
            max_tokens=10,
            temperature=0.0
        )
        latency = time.time() - start
        msg = resp.choices[0].message.content.strip()
        print(f"\n[SUCCESS] Server responded in {latency:.2f} seconds.")
        print(f"[REPLY] {msg}")
        
        if latency > 15.0:
            print("\n[WARNING] Latency is high (>15s). Ensure batch sizes are kept to 1 and async extraction is sequential.")
        else:
            print("\n[INFO] Latency is good. Model should support parallel generations.")
            
    except Exception as e:
        print(f"\n[ERROR] Failed to connect or generate: {e}")
        sys.exit(1)

def tune_profile(npc_key, temperature, max_tokens):
    if temperature is None and max_tokens is None:
        print("[ERROR] Nothing to update. Pass --temp and/or --tokens.")
        sys.exit(1)

    if not PROFILES_PATH.exists():
        print(f"[ERROR] Profiles file not found at {PROFILES_PATH}")
        sys.exit(1)
        
    try:
        data = json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[ERROR] Could not parse json: {e}")
        sys.exit(1)
        
    profiles = data.get("profiles", {})
    if npc_key not in profiles:
        print(f"[ERROR] Profile '{npc_key}' not found in configs.")
        print(f"Available profiles: {list(profiles.keys())}")
        sys.exit(1)
        
    profile = profiles[npc_key]
    if "generation_defaults" not in profile:
        profile["generation_defaults"] = {}
        
    if temperature is not None:
        profile["generation_defaults"]["temperature"] = temperature
    if max_tokens is not None:
        profile["generation_defaults"]["max_response_tokens"] = max_tokens
        
    PROFILES_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[SUCCESS] Updated {npc_key} generation defaults: {profile['generation_defaults']}")

# CLI entry

def main():
    parser = argparse.ArgumentParser(description="Automate LLM tuning, connectivity testing, and LM Studio remote management.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # ── NPC PIPELINE COMMANDS ──
    test_p = subparsers.add_parser("test-connection", help="Benchmark generation latency")
    test_p.add_argument("--url", default="http://127.0.0.1:1234/v1", help="Base URL of local inference server")
    test_p.add_argument("--model", default="local-model", help="Model identifier to test")
    
    tune_p = subparsers.add_parser("tune", help="Tune a profile's generation defaults")
    tune_p.add_argument("--npc", required=True, help="Profile key")
    tune_p.add_argument("--temp", type=float, help="Temperature float (e.g. 0.8)")
    tune_p.add_argument("--tokens", type=int, help="Max tokens int (e.g. 150)")
    
    # ── LM STUDIO SERVER COMMANDS ──
    subparsers.add_parser("lm-list", help="List currently loaded models via LM Studio REST API")
    
    lm_load_p = subparsers.add_parser("lm-load", help="Load a model into LM Studio memory")
    lm_load_p.add_argument("model_id", help="HuggingFace ID or local identifier (e.g. ibm/granite-4-micro)")
    
    lm_unload_p = subparsers.add_parser("lm-unload", help="Unload a model from LM Studio memory")
    lm_unload_p.add_argument("model_id", help="Model identifier to unload")
    
    lm_download_p = subparsers.add_parser("lm-download", help="Start downloading a model to LM Studio")
    lm_download_p.add_argument("model_id", help="HuggingFace model ID (e.g. TheBloke/Llama-2-7B-GGUF)")

    args = parser.parse_args()
    
    if args.command == "test-connection":
        test_connection(args.url, args.model)
    elif args.command == "tune":
        tune_profile(args.npc, args.temp, args.tokens)
    elif args.command == "lm-list":
        lm_list()
    elif args.command == "lm-load":
        lm_load(args.model_id)
    elif args.command == "lm-unload":
        lm_unload(args.model_id)
    elif args.command == "lm-download":
        lm_download(args.model_id)

if __name__ == "__main__":
    main()
