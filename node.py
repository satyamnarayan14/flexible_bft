# node.py
# Simplified HotStuff-style replica (leader-based). Works within SimulatedNetwork.
import asyncio
from collections import defaultdict
from typing import Dict, List, Optional
from utils import Block, Vote, QC, simple_sign, now_ms
import utils

class Replica:
    def __init__(self, node_id: str, privkey: str, all_ids: List[str], network, f: int, is_byzantine=False, is_abc=False):
        self.id = node_id
        self.priv = privkey
        self.all_ids = all_ids
        self.network = network  # SimulatedNetwork instance
        self.f = f
        self.n = len(all_ids)
        self.is_byzantine = is_byzantine
        self.is_abc = is_abc  # alive-but-corrupt (behavioral hook)
        # storage
        self.blocks: Dict[str, Block] = {}
        self.high_qc: Optional[QC] = None
        self.votes_collected: Dict[str, List[Vote]] = defaultdict(list)
        self.committed: List[str] = []
        self.current_view = 0
        self.leader_func = lambda view: all_ids[view % len(all_ids)]
        # inbox queue
        self.inbox = asyncio.Queue()
        self.running = False
        # register to network
        self.network.register(self.id, self.receive)

    async def receive(self, msg):
        await self.inbox.put(msg)

    async def send(self, dst, msg):
        await self.network.send(self.id, dst, msg)

    async def broadcast(self, msg):
        await self.network.broadcast(self.id, msg)

    def make_block(self, payload: str):
        parent_id = None
        if self.blocks:
            # last block by height
            max_h = max(b.height for b in self.blocks.values())
            parent = [b for b in self.blocks.values() if b.height == max_h][0]
            parent_id = parent.id
            height = max_h + 1
        else:
            height = 0
            parent_id = None
        block = Block(height=height, parent_id=parent_id, proposer=self.id, payload=payload, view=self.current_view)
        return block

    async def propose_loop(self, propose_interval=0.2):
        """If leader, periodically propose."""
        while self.running:
            leader = self.leader_func(self.current_view)
            if leader == self.id:
                # propose a block
                payload = f"tx_from_{self.id}_{now_ms()}"
                block = self.make_block(payload)
                # optionally include justify QC id
                if self.high_qc:
                    block.justify_qc_id = self.high_qc.id()
                self.blocks[block.id] = block
                msg = {"type":"PROPOSE", "from": self.id, "view": self.current_view, "block": block}
                # Byzantine leader may equivocate: broadcast two conflicting proposals for same view
                if self.is_byzantine:
                    # create two different blocks with same view to equivocate
                    block2 = self.make_block(payload + "_alt")
                    self.blocks[block2.id] = block2
                    msg2 = {"type":"PROPOSE", "from": self.id, "view": self.current_view, "block": block2}
                    # send both
                    await self.broadcast(msg)
                    await self.broadcast(msg2)
                else:
                    await self.broadcast(msg)
            await asyncio.sleep(propose_interval)

    async def process_messages(self):
        while self.running:
            msg = await self.inbox.get()
            try:
                await self.on_message(msg)
            except Exception as e:
                print(f"[{self.id}] error handling msg {msg}: {e}")

    async def on_message(self, msg):
        mtype = msg.get("type")
        if mtype == "PROPOSE":
            await self.on_propose(msg)
        elif mtype == "VOTE":
            await self.on_vote(msg)
        elif mtype == "QC":
            await self.on_qc(msg)
        elif mtype == "NEWVIEW":
            # simple: accept and update view
            incoming_view = msg.get("view")
            if incoming_view > self.current_view:
                self.current_view = incoming_view
        else:
            pass

    async def on_propose(self, msg):
        block: Block = msg["block"]
        # store block
        self.blocks[block.id] = block
        # validate: naive: always valid unless conflicts with locked QC (not modeled)
        # If byzantine replica, behave arbitrarily: may vote for any proposal or multiple proposals
        # If ABC replica: if it can break safety it may, else it helps progress (simplified)
        # For simplicity, honest replicas vote once per view for the first proposal seen
        # We track votes_collected to ensure per-view single vote
        # create vote
        vote_sig = simple_sign(self.priv, f"{block.id}:{block.view}")
        vote = Vote(block_id=block.id, voter=self.id, view=block.view, sig=vote_sig)
        # send vote to leader of view
        leader = self.leader_func(block.view)
        if self.is_byzantine:
            # may equivocate: vote for multiple conflicting blocks (here we vote for this one too)
            # We'll just send vote (byzantine behavior simulated at leader)
            await self.send(leader, {"type":"VOTE", "from": self.id, "vote": vote})
        elif self.is_abc:
            # ABC: simulate that it votes for this block if it does not break safety,
            # otherwise vote in a way to break safety (hard to model); simplified: behave like honest with some probability
            import random
            if random.random() < 0.8:
                await self.send(leader, {"type":"VOTE", "from": self.id, "vote": vote})
            else:
                # temporarily abstain or send delayed vote (simulate not blocking progress)
                await asyncio.sleep(0.01)
                await self.send(leader, {"type":"VOTE", "from": self.id, "vote": vote})
        else:
            await self.send(leader, {"type":"VOTE", "from": self.id, "vote": vote})

    async def on_vote(self, msg):
        vote: Vote = msg["vote"]
        # only leader collects votes for their view
        leader = self.leader_func(vote.view)
        if leader != self.id:
            return
        # collect
        lst = self.votes_collected[vote.block_id]
        # avoid duplicate voter entries
        if vote.voter in [v.voter for v in lst]:
            return
        lst.append(vote)
        # if reach threshold, form QC and broadcast
        if len(lst) >= (2 * self.f + 1):
            # build combined_sig naive: concat sigs
            signer_ids = [v.voter for v in lst]
            combined = hashlib = __import__("hashlib")
            combined_sig = combined.sha256((",".join([v.sig for v in lst])).encode()).hexdigest()
            qc = QC(block_id=vote.block_id, signer_ids=signer_ids, combined_sig=combined_sig, view=vote.view)
            # broadcast QC
            await self.broadcast({"type":"QC", "from": self.id, "qc": qc})
            # record high_qc
            self.high_qc = qc

    async def on_qc(self, msg):
        qc: QC = msg["qc"]
        # store QC metadata - for simplicity we mark high_qc
        self.high_qc = qc
        # in this simplified model, commit when we see chain length 3 QCs
        # we track parent chain using blocks stored: if block B has QC, and its parent has QC, etc.
        # mark commit for block ancestor 2 back
        blk = self.blocks.get(qc.block_id)
        if not blk:
            return
        # naive: look for parent and grandparent
        parent = self.blocks.get(blk.parent_id) if blk.parent_id else None
        grandparent = self.blocks.get(parent.parent_id) if parent and parent.parent_id else None
        if grandparent:
            # commit grandparent if not already
            if grandparent.id not in self.committed:
                self.committed.append(grandparent.id)
                print(f"[{self.id}] COMMIT block height={grandparent.height} id={grandparent.id[:8]} (proposed by {grandparent.proposer})")

    async def start(self):
        self.running = True
        self._task = asyncio.create_task(self.process_messages())
        self._propose_task = asyncio.create_task(self.propose_loop(0.15))

    async def stop(self):
        self.running = False
        self._task.cancel()
        self._propose_task.cancel()
