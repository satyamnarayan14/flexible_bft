# learner.py
# Learner that watches transcript and applies local commit rules
import asyncio
from typing import Dict, Any
from utils import QC

class Learner:
    def __init__(self, name: str, network, subscribe_to: list, q_threshold_fast: int, q_threshold_commit: int, rely_on_timing=False, delta_ms=500):
        """
        subscribe_to: list of replica ids to listen to (in simulation we register with network)
        q_threshold_fast: small threshold for fast commit (may be risky)
        q_threshold_commit: higher threshold for safe commit
        """
        self.name = name
        self.network = network
        self.subs = subscribe_to
        self.q_fast = q_threshold_fast
        self.q_commit = q_threshold_commit
        self.rely_on_timing = rely_on_timing
        self.delta_ms = delta_ms
        self.inbox = asyncio.Queue()
        self.committed = []
        # register with network: for simplicity we register one listener id (learners get broadcasts)
        self.network.register(f"learner_{name}", self.receive)

    async def receive(self, msg):
        # learners will get QC broadcasts as network broadcasts to all nodes including learners
        await self.inbox.put(msg)

    async def run(self):
        while True:
            msg = await self.inbox.get()
            if msg.get("type") == "QC":
                qc: QC = msg["qc"]
                # fast decision
                if len(qc.signer_ids) >= self.q_fast and qc.block_id not in self.committed:
                    # fast commit (optionally check timing)
                    print(f"[Learner {self.name}] FAST-commit candidate block {qc.block_id[:8]} with {len(qc.signer_ids)} sigs")
                    self.committed.append(qc.block_id)
                # safe commit
                if len(qc.signer_ids) >= self.q_commit and qc.block_id not in self.committed:
                    print(f"[Learner {self.name}] SAFE-commit block {qc.block_id[:8]} with {len(qc.signer_ids)} sigs")
                    self.committed.append(qc.block_id)
            # ignore other messages
