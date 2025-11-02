# network.py
# Simulated network delivering messages between in-process nodes with optional delay and drops.
import asyncio
import random
from typing import Callable, Dict, Any

class SimulatedNetwork:
    def __init__(self, drop_rate=0.0, min_delay=0.01, max_delay=0.05, loop=None):
        self.nodes = {}  # id -> inbox coroutine/callable
        self.drop_rate = drop_rate
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.loop = loop or asyncio.get_event_loop()

    def register(self, node_id: str, deliver_fn: Callable[[Dict[str,Any]], None]):
        """Register a callable to deliver messages to (node's inbox)."""
        self.nodes[node_id] = deliver_fn

    async def send(self, src: str, dst: str, msg: Dict[str,Any]):
        if dst not in self.nodes:
            # drop silently
            return
        if random.random() < self.drop_rate:
            # simulate drop
            return
        delay = random.uniform(self.min_delay, self.max_delay)
        await asyncio.sleep(delay)
        # deliver
        await self.nodes[dst](msg)

    async def broadcast(self, src: str, msg: Dict[str,Any]):
        tasks = []
        for dst in list(self.nodes.keys()):
            # broadcast includes sending to self as well
            tasks.append(self.loop.create_task(self.send(src, dst, msg)))
        if tasks:
            await asyncio.gather(*tasks)
