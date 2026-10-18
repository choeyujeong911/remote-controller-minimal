"""필요 패키지: psutil. 실행: python agent.py http://중앙서버IP:8000"""
import json
import os
import socket
import sys
import time
import uuid
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import psutil

SERVER = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
ID_FILE = Path(__file__).with_name(".agent-id")
if not ID_FILE.exists():
    ID_FILE.write_text(str(uuid.uuid4()), encoding="utf-8")
AGENT_ID = str(uuid.UUID(ID_FILE.read_text(encoding="utf-8").strip()))


def post(path, body):
    request = Request(SERVER + path, json.dumps(body).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=2) as response:
        return json.load(response)


def register():
    # 서버로 가는 경로의 LAN IP. UDP connect 자체는 패킷을 보내지 않는다.
    host = socket.gethostbyname(urlsplit(SERVER).hostname)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect((host, 8000))
        ip = sock.getsockname()[0]
    mac = ":".join(f"{uuid.getnode():012x}"[i:i + 2] for i in range(0, 12, 2))
    post("/api/agents/register", {
        "agent_id": AGENT_ID, "device_name": socket.gethostname(),
        "mac_address": os.getenv("AGENT_MAC", mac),
        "ip_address": os.getenv("AGENT_IP", ip),
        "ws_port": int(os.getenv("AGENT_WS_PORT", "8765")),
    })
    print(f"등록: {socket.gethostname()} ({AGENT_ID})", flush=True)


if __name__ == "__main__":
    registered = False
    try:
        psutil.cpu_percent()  # 첫 호출은 기준값만 설정한다.
        time.sleep(1)
        while True:
            started = time.monotonic()
            try:
                if not registered:
                    register()
                    registered = True
                post(f"/api/agents/{AGENT_ID}/status", {
                    "status": "부재중", "cpu_percent": psutil.cpu_percent(),
                    "memory_percent": psutil.virtual_memory().percent,
                })
            except (OSError, URLError, ValueError) as error:
                registered = False
                print(f"통신 실패: {error}", flush=True)
            time.sleep(max(0, 1 - (time.monotonic() - started)))
    except KeyboardInterrupt:
        print("에이전트 종료")