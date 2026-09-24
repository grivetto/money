#!/usr/bin/env python3
"""
TOOL: state_manager
Layer 3 — Atomic state persistence (read/write)
Input:  action (read/write), optional state_json as arg
Output: current state dict
State file: .tmp/gridbotv4_state.json
"""
import sys
import json
from pathlib import Path

STATE_FILE = Path(__file__).parent.parent / ".tmp" / "gridbotv4_state.json"

def read_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return None

def write_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)

def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "read"

    if action == "read":
        state = read_state()
        print(json.dumps(state if state else {"status": "empty"}))
    elif action == "write":
        if len(sys.argv) > 2:
            state = json.loads(sys.argv[2])
        else:
            state = json.loads(sys.stdin.read())
        write_state(state)
        print(json.dumps({"status": "saved"}))
    elif action == "merge":
        if len(sys.argv) > 2:
            patch = json.loads(sys.argv[2])
        else:
            patch = json.loads(sys.stdin.read())
        current = read_state() or {}
        current.update(patch)
        write_state(current)
        print(json.dumps({"status": "merged"}))
    else:
        print(json.dumps({"error": f"Unknown action: {action}"}))

if __name__ == "__main__":
    main()
