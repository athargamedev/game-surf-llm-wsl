#!/usr/bin/env python3
"""
Automatic diagnostic script for Game_Surf Supabase memory workflow.
Checks each step of the memory pipeline and reports status.
"""

import subprocess
import json
import sys
from pathlib import Path

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'

def run_command(cmd):
    """Run a shell command and return output."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", 124

def print_header(title):
    print(f"\n{BOLD}{BLUE}{'='*60}{RESET}")
    print(f"{BOLD}{BLUE}{title:^60}{RESET}")
    print(f"{BOLD}{BLUE}{'='*60}{RESET}\n")

def print_check(name, status, details=""):
    status_str = f"{GREEN}✓ PASS{RESET}" if status else f"{RED}✗ FAIL{RESET}"
    print(f"{status_str} {name}")
    if details:
        print(f"   {YELLOW}→ {details}{RESET}")

def check_supabase_connection():
    """Check if Supabase is connected."""
    print_header("PHASE 1: Supabase Connection")
    
    out, code = run_command("curl -s http://127.0.0.1:8000/status 2>/dev/null | python3 -c \"import sys, json; d=json.load(sys.stdin); print('ENABLED:' + str(d.get('supabase_enabled', False)) + '|CONNECTED:' + str(d.get('supabase_connected', False)))\" 2>/dev/null")
    
    if not out:
        print_check(False, "Backend /status endpoint", "Server not responding")
        return False
    
    try:
        enabled, connected = out.split('|')
        enabled = enabled.split(':')[1] == 'True'
        connected = connected.split(':')[1] == 'True'
        
        print_check(enabled, "Supabase enabled in .env")
        print_check(connected, "Supabase connection working")
        
        return connected
    except:
        print_check(False, "Supabase connection", "Could not parse response")
        return False

def check_database_tables():
    """Check if key tables have data."""
    print_header("PHASE 2: Database Table Inspection")
    
    # Try to get DATABASE_URL from environment
    db_url = subprocess.run("echo $DATABASE_URL", shell=True, capture_output=True, text=True).stdout.strip()
    
    if not db_url:
        print(f"{YELLOW}⚠ DATABASE_URL not set. Skipping database checks.{RESET}")
        print(f"{YELLOW}   Set it with: export DATABASE_URL='postgresql://...'  {RESET}\n")
        return None
    
    checks = {
        "dialogue_turns": "SELECT COUNT(*) FROM dialogue_turns;",
        "dialogue_sessions": "SELECT COUNT(*) FROM dialogue_sessions;",
        "npc_memories": "SELECT COUNT(*) FROM npc_memories;",
    }
    
    results = {}
    for table_name, query in checks.items():
        cmd = f"psql $DATABASE_URL -t -c \"{query}\" 2>/dev/null"
        out, code = run_command(cmd)
        
        try:
            count = int(out.strip()) if out.strip() else 0
            results[table_name] = count
            has_data = count > 0
            print_check(has_data, f"{table_name:20} ({count:4} rows)", 
                       "✓ Data present" if has_data else "Empty - messages not saved yet")
        except:
            print_check(False, f"{table_name:20}", "Could not query")
            results[table_name] = 0
    
    return results

def check_session_status():
    """Check if sessions are being marked as ended."""
    print_header("PHASE 3: Session Status Check")
    
    db_url = subprocess.run("echo $DATABASE_URL", shell=True, capture_output=True, text=True).stdout.strip()
    
    if not db_url:
        print(f"{YELLOW}⚠ DATABASE_URL not set. Skipping database checks.{RESET}\n")
        return None
    
    cmd = '''psql $DATABASE_URL -t -c "SELECT 
        SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) as active_sessions,
        SUM(CASE WHEN status='ended' THEN 1 ELSE 0 END) as ended_sessions
    FROM dialogue_sessions;" 2>/dev/null'''
    
    out, code = run_command(cmd)
    
    if not out or '|' not in out:
        print_check(False, "Session status query", "Could not retrieve data")
        return None
    
    try:
        active, ended = out.split('|')
        active = int(active.strip()) if active.strip() and active.strip() != 'None' else 0
        ended = int(ended.strip()) if ended.strip() and ended.strip() != 'None' else 0
        
        print(f"  Active sessions: {BLUE}{active}{RESET}")
        print(f"  Ended sessions:  {BLUE}{ended}{RESET}")
        print()
        
        if active > 0:
            print(f"{YELLOW}⚠ Note: Sessions still marked as 'active' may not have been ended properly.{RESET}")
            print(f"{YELLOW}   Sessions need status='ended' to trigger memory summarization.{RESET}\n")
        
        return {"active": active, "ended": ended}
    except:
        print_check(False, "Session parsing", f"Invalid output: {out}")
        return None

def check_memory_summarization():
    """Check if summarize_dialogue_session trigger exists."""
    print_header("PHASE 4: Memory Summarization Trigger")
    
    db_url = subprocess.run("echo $DATABASE_URL", shell=True, capture_output=True, text=True).stdout.strip()
    
    if not db_url:
        print(f"{YELLOW}⚠ DATABASE_URL not set. Skipping database checks.{RESET}\n")
        return None
    
    cmd = '''psql $DATABASE_URL -t -c "SELECT COUNT(*) FROM information_schema.triggers 
    WHERE trigger_name='trg_summarize_ended_dialogue_session';" 2>/dev/null'''
    
    out, code = run_command(cmd)
    
    try:
        trigger_exists = int(out.strip() or 0) > 0
        print_check(trigger_exists, "Trigger 'trg_summarize_ended_dialogue_session' exists")
        
        if trigger_exists:
            print(f"   {GREEN}→ Trigger is installed and should auto-summarize sessions{RESET}")
        else:
            print(f"   {RED}→ Trigger missing! Memory won't be created automatically.{RESET}")
            print(f"   {YELLOW}→ Re-apply migrations: cd supabase && supabase migration up{RESET}\n")
        
        return trigger_exists
    except:
        print_check(False, "Trigger check", "Could not query")
        return None

def recommend_next_steps(results):
    """Provide targeted recommendations based on results."""
    print_header("DIAGNOSIS & RECOMMENDATIONS")
    
    if not results:
        print(f"{YELLOW}Unable to run full diagnostics.{RESET}\n")
        return
    
    turn_count = results.get("dialogue_turns", 0)
    session_count = results.get("dialogue_sessions", 0)
    memory_count = results.get("npc_memories", 0)
    
    print(f"{BOLD}Current State:{RESET}")
    print(f"  • Dialogue turns (messages):  {BLUE}{turn_count}{RESET}")
    print(f"  • Sessions:                   {BLUE}{session_count}{RESET}")
    print(f"  • NPC memories:               {BLUE}{memory_count}{RESET}")
    print()
    
    if turn_count == 0:
        print(f"{RED}ISSUE: No dialogue turns recorded.{RESET}")
        print(f"  {YELLOW}Root cause: Messages not being saved to database{RESET}")
        print(f"  {BLUE}Action: {RESET}")
        print(f"    1. Check that Supabase is enabled: ENABLE_SUPABASE=true in .env")
        print(f"    2. Send a test message via chat_interface.html")
        print(f"    3. Check server logs for 'Supabase write error'")
        print(f"    4. Verify dialogue_turns table structure: psql \\$DATABASE_URL -d+ dialogue_turns")
        print()
    elif session_count == 0:
        print(f"{RED}ISSUE: No sessions recorded.{RESET}")
        print(f"  {YELLOW}Root cause: /session/start not being called{RESET}")
        print(f"  {BLUE}Action: {RESET}")
        print(f"    1. Check chat_interface.html is calling /session/start on page load")
        print(f"    2. Check browser console for fetch errors")
        print()
    elif memory_count == 0:
        print(f"{YELLOW}ISSUE: Messages and sessions exist but no memories created.{RESET}")
        print(f"  {YELLOW}Root cause: Memory summarization not triggering{RESET}")
        print(f"  {BLUE}Action: {RESET}")
        print(f"    1. Verify sessions are marked as 'ended' (see Phase 3 above)")
        print(f"    2. Check that trigger exists: run 'psql $DATABASE_URL -c")
        print(f"       \"SELECT * FROM information_schema.triggers")
        print(f"       WHERE trigger_name='trg_summarize_ended_dialogue_session';\"'")
        print(f"    3. If trigger missing, re-apply migrations:")
        print(f"       cd supabase && supabase migration up")
        print(f"    4. Manually test trigger:")
        print(f"       UPDATE dialogue_sessions SET status='ended' WHERE id=(SELECT id FROM")
        print(f"       dialogue_sessions LIMIT 1);")
        print(f"       Then check npc_memories for new records")
        print()
    else:
        print(f"{GREEN}✓ Database pipeline working!{RESET}")
        print(f"  {GREEN}Memories are being created successfully.{RESET}")
        print(f"  {BLUE}Next: {RESET}")
        print(f"    1. Test if memory is being loaded in next session:")
        print(f"       POST /session/start and check 'memory_summary' in response")
        print(f"    2. If memory_summary is empty but npc_memories has data:")
        print(f"       Issue is in load_player_context() function")
        print(f"    3. If memory_summary has data but NPC doesn't use it:")
        print(f"       Issue is in system prompt injection")
        print()

def main():
    print(f"\n{BOLD}Game_Surf Memory Workflow Diagnostic{RESET}")
    print(f"{BOLD}{'='*60}{RESET}\n")
    
    # Check Supabase connection
    connected = check_supabase_connection()
    
    # Check database tables
    table_results = check_database_tables()
    
    # Check session status
    session_status = check_session_status()
    
    # Check memory summarization trigger
    trigger_exists = check_memory_summarization()
    
    # Provide recommendations
    if table_results:
        recommend_next_steps(table_results)
    
    print(f"{BOLD}For detailed diagnostic steps, see:{RESET}")
    print(f"  {BLUE}docs/MEMORY_WORKFLOW_TEST_PLAN.md{RESET}\n")

if __name__ == "__main__":
    main()
