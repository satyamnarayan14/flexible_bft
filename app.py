# app.py
import asyncio
import json
from typing import Dict, List, Any, Callable

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core.network import SimulatedNetwork
from core.node import Replica
from core.learner import Learner
from core.utils import ed25519_keypair
from fastapi.responses import HTMLResponse

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/health")
async def health():
    return {"ok": True}

@app.get("/")
async def root():
    return HTMLResponse("<h1>It works ✅</h1><p>Go to /health for JSON</p>")

class Hub:
    def __init__(self):
        self.clients: List[WebSocket] = []
        self.lock = asyncio.Lock()
    async def connect(self, ws: WebSocket):
        await ws.accept()
        async with self.lock:
            self.clients.append(ws)
    async def disconnect(self, ws: WebSocket):
        async with self.lock:
            if ws in self.clients:
                self.clients.remove(ws)
    async def broadcast(self, message: dict):
        payload = json.dumps(message)
        async with self.lock:
            dead = []
            for ws in self.clients:
                try:    await ws.send_text(payload)
                except: dead.append(ws)
            for d in dead:
                if d in self.clients: self.clients.remove(d)

hub = Hub()

def make_emitter(prefix: str):
    async def _emit_async(evt: dict):
        await hub.broadcast({"source": prefix, **evt})
    def _emit(evt: dict):
        asyncio.get_event_loop().create_task(_emit_async(evt))
    return _emit

sim_tasks: List[asyncio.Task] = []
sim_running = False

@app.get("/")
async def index():
    return FileResponse("static/index.html")

@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            if msg.get("type") == "START":
                await start_simulation(msg.get("config", {}))
            elif msg.get("type") == "STOP":
                await stop_simulation()
    except:
        await hub.disconnect(ws)

async def stop_simulation():
    global sim_tasks, sim_running
    if sim_running:
        for t in sim_tasks:
            t.cancel()
        sim_tasks = []
        sim_running = False
        await hub.broadcast({"type":"STATUS","state":"stopped"})

async def start_simulation(cfg: Dict[str, Any]):
    await stop_simulation()
    await hub.broadcast({"type":"STATUS","state":"starting"})

    n = int(cfg.get("replicas", 7))
    f = int(cfg.get("f", 2))
    byz = set(cfg.get("byzantine", []))
    abc = set(cfg.get("abc", []))
    qc_threshold = cfg.get("qc_threshold", None)
    drop_rate = float(cfg.get("drop_rate", 0.0))
    min_delay = float(cfg.get("min_delay", 0.01))
    max_delay = float(cfg.get("max_delay", 0.05))
    propose_interval = float(cfg.get("propose_interval", 0.15))
    duration = float(cfg.get("duration", 10))
    learners_spec = cfg.get("learners", [
        {"name":"fast","q_fast":4,"q_commit":6},
        {"name":"safe","q_fast":999,"q_commit":2*f+1}
    ])

    if n < (3*f + 1):
        await hub.broadcast({"type":"WARN","message":f"n={n} < 3f+1={3*f+1} may violate classical safety."})

    loop = asyncio.get_event_loop()
    net = SimulatedNetwork(drop_rate=drop_rate, min_delay=min_delay, max_delay=max_delay, loop=loop)

    ids = [f"R{i}" for i in range(n)]
    keypairs = {}
    pubkeys = {}
    for nid in ids:
        sk, vk = ed25519_keypair()
        keypairs[nid] = (sk, vk)
        pubkeys[nid] = vk

    emitter_r = make_emitter("replica")
    replicas = {}
    for i, nid in enumerate(ids):
        r = Replica(
            node_id=nid,
            keypair=keypairs[nid],
            all_ids=ids,
            pubkeys=pubkeys,
            network=net,
            f=f,
            qc_threshold=qc_threshold,
            is_byzantine=(i in byz),
            is_abc=(i in abc),
            propose_interval=propose_interval,
            emit=emitter_r,
        )
        replicas[nid] = r

    emitter_l = make_emitter("learner")
    learners = []
    for spec in learners_spec:
        name = spec["name"]
        q_fast = int(spec.get("q_fast", 999999))
        q_commit = int(spec.get("q_commit", 2*f+1))
        ln = Learner(
            name=name,
            network=net,
            q_threshold_fast=q_fast,
            q_threshold_commit=q_commit,
            rely_on_timing=False,
            delta_ms=500,
            emit=emitter_l,
        )
        learners.append(ln)

    global sim_tasks, sim_running
    sim_tasks = []
    for r in replicas.values():
        sim_tasks.append(asyncio.create_task(r.start()))
    for l in learners:
        sim_tasks.append(asyncio.create_task(l.run()))

    async def _timer():
        await asyncio.sleep(duration)
        await stop_simulation()
        await hub.broadcast({"type":"STATUS","state":"finished"})
    sim_tasks.append(asyncio.create_task(_timer()))
    sim_running = True

    await hub.broadcast({
        "type":"STATUS","state":"running",
        "config":{
            "replicas": n, "f": f, "byzantine": list(byz), "abc": list(abc),
            "qc_threshold": qc_threshold, "drop_rate": drop_rate,
            "min_delay": min_delay, "max_delay": max_delay,
            "propose_interval": propose_interval, "duration": duration,
            "learners": learners_spec
        }
    })
