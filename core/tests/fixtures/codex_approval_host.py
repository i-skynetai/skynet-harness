"""Offline JSON-RPC peer: no model, credentials or operating-system approvals."""
import json
import sys
import time

mode = sys.argv[1]


def send(value):
    print(json.dumps(value), flush=True)


for line in sys.stdin:
    message = json.loads(line)
    if mode == "disconnect":
        break
    if mode == "timeout":
        time.sleep(60)
    if message.get("method") == "initialize":
        send({"id": message["id"], "result": {}})
    elif message.get("method") == "config/read":
        send({"id": message["id"], "result": {"config": {
            "mcp_servers": {"sky_kb": {"enabled_tools": ["search"]}}}}})
    elif message.get("method") == "thread/start":
        send({"id": message["id"], "result": {"thread": {"id": "thread"},
              "sandbox": {"type": "readOnly", "networkAccess": mode == "network"},
              "approvalPolicy": "untrusted", "approvalsReviewer": "user"}})
    elif message.get("method") == "turn/start":
        send({"method": "turn/started", "params": {"turn": {"id": "turn"}}})
        if mode == "unknown":
            send({"id": 20, "method": "future/approveEverything", "params": {}})
        elif mode == "malformed":
            print("not JSON", flush=True)
        else:
            send({"method": "turn/completed", "params": {"turn": {"status": "completed"}}})
