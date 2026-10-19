"""필요 패키지: psutil. 실행: python agent.py http://중앙서버IP:8000"""
import ctypes
import json
import os
import socket
import sys
import time
import uuid
from ctypes import wintypes
from urllib.error import URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

import psutil

SERVER = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
IDLE_SECONDS = 10  # 디버깅용 부재 기준
DEVICE_NAME = socket.gethostname()
MAC_ADDRESS = os.getenv("AGENT_MAC", ":".join(f"{uuid.getnode():012X}"[i:i + 2] for i in range(0, 12, 2))).upper()
AGENT_ID = f"{DEVICE_NAME}-{MAC_ADDRESS.replace(':', '')[-6:]}"


class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def idle_seconds():
    info = LASTINPUTINFO(ctypes.sizeof(LASTINPUTINFO), 0)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        raise OSError("마지막 입력 시각 조회 실패")
    idle_ms = (ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF
    return idle_ms / 1000


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
    post("/api/agents/register", {
        "agent_id": AGENT_ID, "device_name": DEVICE_NAME,
        "mac_address": MAC_ADDRESS,
        "ip_address": os.getenv("AGENT_IP", ip),
        "ws_port": int(os.getenv("AGENT_WS_PORT", "8765")),
    })
    print(f"등록: {DEVICE_NAME} ({AGENT_ID})", flush=True)


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
                idle = idle_seconds()
                post(f"/api/agents/{quote(AGENT_ID, safe='')}/status", {
                    "status": "사용중" if idle < IDLE_SECONDS else "부재중",
                    "idle_seconds": idle, "cpu_percent": psutil.cpu_percent(),
                    "memory_percent": psutil.virtual_memory().percent,
                })
            except (OSError, URLError, ValueError) as error:
                registered = False
                print(f"통신 실패: {error}", flush=True)
            time.sleep(max(0, 1 - (time.monotonic() - started)))
    except KeyboardInterrupt:
        print("에이전트 종료")