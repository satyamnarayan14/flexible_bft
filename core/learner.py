# core/learner.py
import asyncio
from typing import Callable, Optional
from .utils import QC

class Learner:
    def __init__(
        self,
        name: str,
        network,
        q_threshold_fast: int,
        q_threshold_commit: int,
        rely_on_timing: bool = False,
        delta_ms: int = 500,
        emit: Optional[Callable[[dict], None]] = None,
    ):
        self.name = name
        self.network = network
        self.q_fast = q_threshold_fast
        self.q_commit = q_threshold_commit
        self.rely_on_timing = rely_on_timing
        self.delta_ms = delta_ms

        self.inbox = asyncio.Queue()
        self.committed = []
        self.emit = emit or (lambda e: None)

        self.network.register(f"learner_{name}", self.receive)

    async def receive(self, msg):
        await self.inbox.put(msg)

    async def run(self):
        while True:
            msg = await self.inbox.get()
            if msg.get("type") != "QC":
                continue
            qc: QC = msg["qc"]
            if len(qc.signer_ids) >= self.q_fast and qc.block_id not in self.committed:
                self.committed.append(qc.block_id)
                self.emit({"type":"LEARNER_FAST","learner":self.name,
                           "block_id":qc.block_id,"sigs":len(qc.signer_ids)})
            if len(qc.signer_ids) >= self.q_commit and qc.block_id not in self.committed:
                self.committed.append(qc.block_id)
                self.emit({"type":"LEARNER_SAFE","learner":self.name,
                           "block_id":qc.block_id,"sigs":len(qc.signer_ids)})
