# core/node.py
import asyncio
import hashlib
from collections import defaultdict
from typing import Dict, List, Optional, Callable, Tuple

from .utils import Block, Vote, QC, now_ms, ed25519_sign, ed25519_verify

VIEW_TIMEOUT_SEC = 0.8  # demo-friendly; adjust in app config if you like

class Replica:
    def __init__(
        self,
        node_id: str,
        keypair: Tuple[bytes, bytes],  # (sk, vk)
        all_ids: List[str],
        pubkeys: Dict[str, bytes],     # node_id -> vk
        network,
        f: int,
        qc_threshold: Optional[int] = None,
        is_byzantine: bool = False,
        is_abc: bool = False,
        propose_interval: float = 0.15,
        emit: Optional[Callable[[dict], None]] = None,
    ):
        self.id = node_id
        self.sk, self.vk = keypair
        self.pubkeys = pubkeys

        self.all_ids = all_ids
        self.network = network
        self.f = f
        self.n = len(all_ids)
        self.qc_threshold = qc_threshold if qc_threshold is not None else (2 * f + 1)

        self.is_byzantine = is_byzantine
        self.is_abc = is_abc

        self.blocks: Dict[str, Block] = {}
        self.high_qc: Optional[QC] = None
        self.locked_qc: Optional[QC] = None  # HotStuff locking rule
        self.votes_collected: Dict[str, List[Vote]] = defaultdict(list)
        self.voted_in_view: Dict[int, str] = {}  # view -> block_id
        self.committed: List[str] = []

        self.current_view = 0
        self.leader_func = lambda view: all_ids[view % len(all_ids)]
        self.propose_interval = propose_interval

        self.inbox = asyncio.Queue()
        self.running = False
        self.emit = emit or (lambda e: None)

        self.network.register(self.id, self.receive)
        self._timeout_task: Optional[asyncio.Task] = None
        self._newview_buffer: Dict[int, List[QC]] = defaultdict(list)  # view -> list of highQCs from replicas

    # --- network helpers ---
    async def receive(self, msg):
        await self.inbox.put(msg)

    async def send(self, dst, msg):
        await self.network.send(self.id, dst, msg)

    async def broadcast(self, msg):
        await self.network.broadcast(self.id, msg)

    # --- leader timeout management ---
    def _schedule_view_timeout(self, view: int):
        if self._timeout_task:
            self._timeout_task.cancel()
        self._timeout_task = asyncio.create_task(self._timeout(view))

    async def _timeout(self, view: int):
        await asyncio.sleep(VIEW_TIMEOUT_SEC)
        # if still in same view, trigger new-view to move on
        if self.current_view == view:
            # broadcast NEWVIEW with our best QC
            msg = {"type": "NEWVIEW", "from": self.id, "view": view, "high_qc": self._qc_to_wire(self.high_qc)}
            await self.broadcast(msg)
            self.emit({"type": "TIMEOUT", "replica": self.id, "view": view})

    # --- simple chain helpers ---
    def _tip_block(self) -> Optional[Block]:
        if not self.blocks:
            return None
        max_h = max(b.height for b in self.blocks.values())
        return [b for b in self.blocks.values() if b.height == max_h][0]

    def _extends_locked(self, block: Block) -> bool:
        """Safe voting rule: proposal must extend the block pointed by locked_qc."""
        if self.locked_qc is None:
            return True
        # Walk parents from block to see if it contains locked block
        cur = block
        target_id = self.locked_qc.block_id
        steps = 0
        while cur and steps < 1000:
            if cur.id == target_id:
                return True
            if not cur.parent_id:
                return False
            cur = self.blocks.get(cur.parent_id)
            steps += 1
        return False

    def make_block(self, parent: Optional[Block], view: int, payload: str) -> Block:
        parent_id = parent.id if parent else None
        height = (parent.height + 1) if parent else 0
        b = Block(height=height, parent_id=parent_id, proposer=self.id, payload=payload, view=view)
        if self.high_qc:
            b.justify_qc_id = self.high_qc.id()
        return b

    # --- wire QC (serialize/deserialize minimal) ---
    def _qc_to_wire(self, qc: Optional[QC]):
        if qc is None:
            return None
        return {
            "block_id": qc.block_id,
            "signer_ids": qc.signer_ids,
            "signatures": [s.hex() for s in qc.signatures],
            "view": qc.view,
        }

    def _qc_from_wire(self, o) -> Optional[QC]:
        if not o:
            return None
        return QC(
            block_id=o["block_id"],
            signer_ids=o["signer_ids"],
            signatures=[bytes.fromhex(x) for x in o["signatures"]],
            view=o["view"],
        )

    # --- main loops ---
    async def start(self):
        self.running = True
        self._task_proc = asyncio.create_task(self.process_messages())
        self._task_prop = asyncio.create_task(self.propose_loop())
        self._schedule_view_timeout(self.current_view)

    async def stop(self):
        self.running = False
        for t in [getattr(self, "_task_proc", None), getattr(self, "_task_prop", None), self._timeout_task]:
            if t:
                t.cancel()

    async def process_messages(self):
        while self.running:
            msg = await self.inbox.get()
            try:
                await self.on_message(msg)
            except Exception as e:
                self.emit({"type": "ERROR", "replica": self.id, "error": str(e)})

    async def propose_loop(self):
        # leader periodically proposes; real trigger is new-view and QC arrival
        while self.running:
            leader = self.leader_func(self.current_view)
            if leader == self.id:
                parent = self._tip_block()
                payload = f"tx_from_{self.id}_{now_ms()}"
                block = self.make_block(parent, self.current_view, payload)
                # if locked rule would reject our own block, adopt highQC block as parent
                if not self._extends_locked(block):
                    # try to build on locked qc block instead (safer)
                    locked_block = self.blocks.get(self.locked_qc.block_id) if self.locked_qc else parent
                    block = self.make_block(locked_block, self.current_view, payload)
                self.blocks[block.id] = block
                self.emit({"type": "PROPOSED", "replica": self.id, "view": self.current_view,
                           "block": {"id": block.id, "height": block.height, "parent_id": block.parent_id}})
                await self.broadcast({"type": "PROPOSE", "from": self.id, "view": self.current_view, "block": block})
            await asyncio.sleep(self.propose_interval)

    async def on_message(self, msg):
        t = msg.get("type")
        if t == "PROPOSE":
            await self.on_propose(msg)
        elif t == "VOTE":
            await self.on_vote(msg)
        elif t == "QC":
            await self.on_qc(msg)
        elif t == "NEWVIEW":
            await self.on_newview(msg)

    # --- handlers ---
    async def on_propose(self, msg):
        block: Block = msg["block"]
        self.blocks[block.id] = block

        # SAFE VOTING RULE: only vote once per view, and only if extends locked
        if self.voted_in_view.get(block.view):
            return
        if not self._extends_locked(block):
            return

        # sign vote
        vote_msg = f"{block.id}:{block.view}".encode()
        sig = ed25519_sign(self.sk, vote_msg)
        vote = Vote(block_id=block.id, voter=self.id, view=block.view, sig=sig)

        self.emit({"type": "VOTE_SENT", "replica": self.id, "view": block.view,
                   "block_id": block.id, "to": self.leader_func(block.view)})

        await self.send(self.leader_func(block.view), {"type": "VOTE", "from": self.id, "vote": vote})
        self.voted_in_view[block.view] = block.id

    async def on_vote(self, msg):
        vote: Vote = msg["vote"]
        # only the leader of that view collects
        if self.leader_func(vote.view) != self.id:
            return

        # verify vote signature
        voter_vk = self.pubkeys.get(vote.voter)
        if not voter_vk:
            return
        vote_msg = f"{vote.block_id}:{vote.view}".encode()
        if not ed25519_verify(voter_vk, vote_msg, vote.sig):
            self.emit({"type": "ERROR", "replica": self.id, "error": f"Invalid signature from {vote.voter}"})
            return

        lst = self.votes_collected[vote.block_id]
        if vote.voter in [v.voter for v in lst]:
            return
        lst.append(vote)
        self.emit({"type": "VOTE_RCVD", "replica": self.id, "view": vote.view,
                   "block_id": vote.block_id, "voter": vote.voter, "count": len(lst)})

        # form QC if threshold reached
        if len(lst) >= self.qc_threshold:
            signer_ids = [v.voter for v in lst]
            signatures = [v.sig for v in lst]
            qc = QC(block_id=vote.block_id, signer_ids=signer_ids, signatures=signatures, view=vote.view)
            await self.broadcast({"type": "QC", "from": self.id, "qc": qc})
            self.high_qc = qc
            # update locked_qc (HotStuff rule: lock on parent QC when we produce a QC)
            blk = self.blocks.get(qc.block_id)
            parent = self.blocks.get(blk.parent_id) if blk and blk.parent_id else None
            if parent:
                # create a dummy QC for parent if needed (we didn't actually aggregate parent votes here)
                self.locked_qc = QC(block_id=parent.id, signer_ids=signer_ids, signatures=signatures, view=vote.view)
            self.emit({"type": "QC_FORMED", "replica": self.id, "view": vote.view,
                       "block_id": vote.block_id, "sigs": len(signer_ids)})

            # move to next view & schedule timeout
            self.current_view += 1
            self._schedule_view_timeout(self.current_view)

    async def on_qc(self, msg):
        qc: QC = msg["qc"]
        # verify QC votes (re-verify each signature)
        valid = 0
        for voter_id, sig in zip(qc.signer_ids, qc.signatures):
            vk = self.pubkeys.get(voter_id)
            if vk and ed25519_verify(vk, f"{qc.block_id}:{qc.view}".encode(), sig):
                valid += 1
        if valid < self.qc_threshold:
            return  # ignore invalid QC

        self.high_qc = qc
        blk = self.blocks.get(qc.block_id)
        if not blk:
            return
        parent = self.blocks.get(blk.parent_id) if blk.parent_id else None
        grandparent = self.blocks.get(parent.parent_id) if parent and parent.parent_id else None

        # HotStuff 3-chain commit: commit grandparent when QC on child of parent exists
        if grandparent and (grandparent.id not in self.committed):
            self.committed.append(grandparent.id)
            self.emit({"type": "COMMIT", "replica": self.id,
                       "block_id": grandparent.id, "height": grandparent.height,
                       "proposer": grandparent.proposer})

    async def on_newview(self, msg):
        # collect highest QC proposals from replicas stuck in previous view
        v = msg.get("view")
        if v is None:
            return
        high_qc_wire = msg.get("high_qc")
        qc = self._qc_from_wire(high_qc_wire)
        if qc:
            self._newview_buffer[v].append(qc)

        # if we're the next leader, pick highest QC and propose on it
        next_leader = self.leader_func(v + 1)
        if next_leader == self.id:
            # choose highest by view (tie-break arbitrary)
            buf = self._newview_buffer.get(v, [])
            if buf:
                best = max(buf, key=lambda q: q.view)
                self.high_qc = best
                # unlock safer chain if needed
                parent_blk = self.blocks.get(best.block_id)
                if parent_blk:
                    # lock parent for safety going forward (approximation)
                    self.locked_qc = best
            # bump view and schedule timeout
            if self.current_view <= v:
                self.current_view = v + 1
                self._schedule_view_timeout(self.current_view)
