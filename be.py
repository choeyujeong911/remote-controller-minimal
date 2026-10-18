import os
from contextlib import asynccontextmanager
from ipaddress import IPv4Address
from time import monotonic
from typing import Literal
from uuid import UUID

import pymysql
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# 장비 정보는 DB, 최신 상태는 메모리에만 저장한다.
latest = {}
known = set()


def db():
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"), user="controller",
        password=os.getenv("DB_PASSWORD", "study"), database="controller",
        charset="utf8mb4", autocommit=True, cursorclass=pymysql.cursors.DictCursor,
    )


@asynccontextmanager
async def lifespan(app):
    with db() as conn, conn.cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS agents (
            agent_id CHAR(36) PRIMARY KEY, device_name VARCHAR(255) NOT NULL,
            mac_address CHAR(17) NOT NULL, ip_address VARCHAR(15) NOT NULL,
            ws_port INT NOT NULL)""")
        cur.execute("SELECT agent_id FROM agents")
        known.update(row["agent_id"] for row in cur.fetchall())
    yield


app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origin_regex=r"http://[^/]+:8080",
    allow_methods=["GET", "POST"], allow_headers=["Content-Type"],
)


class Agent(BaseModel):
    agent_id: UUID
    device_name: str = Field(min_length=1, max_length=255)
    mac_address: str = Field(pattern=r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
    ip_address: IPv4Address
    ws_port: int = Field(default=8765, ge=1, le=65535)


class Status(BaseModel):
    status: Literal["사용중", "부재중"]
    idle_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    cpu_percent: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    memory_percent: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)


@app.post("/api/agents/register")
def register(agent: Agent):
    values = agent.model_dump(mode="json")
    with db() as conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO agents VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE device_name=VALUES(device_name),
            mac_address=VALUES(mac_address), ip_address=VALUES(ip_address),
            ws_port=VALUES(ws_port)""", tuple(values.values()))
    known.add(str(agent.agent_id))
    return {"agent_id": agent.agent_id}


@app.post("/api/agents/{agent_id}/status")
async def report(agent_id: UUID, body: Status):
    if str(agent_id) not in known:
        raise HTTPException(404, "먼저 장비를 등록하세요.")
    latest[str(agent_id)] = (body.model_dump(), monotonic())
    return {"ok": True}


@app.get("/api/agents")
def agents():
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT * FROM agents ORDER BY device_name, agent_id")
        rows = cur.fetchall()
    now = monotonic()
    for row in rows:
        metrics, received = latest.get(row["agent_id"], ({"status": "확인 중"}, None))
        row.update(cpu_percent=None, memory_percent=None, idle_seconds=None)
        row.update(metrics)
        if received is not None and now - received > 5:
            row.update(status="연결 끊김", cpu_percent=None, memory_percent=None, idle_seconds=None)
    return rows