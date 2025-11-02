# run_simulation.py
import asyncio
from network import SimulatedNetwork
from node import Replica
from learner import Learner
import simulate_configs as configs
import secrets, hashlib

async def main():
    cfg = configs.config_byzantine_one()  # choose scenario
    n = cfg["n"]
    f = cfg["f"]
    byz = cfg["byzantine"]
    abc = cfg["abc"]
    net = SimulatedNetwork(drop_rate=cfg["drop_rate"], min_delay=cfg["min_delay"], max_delay=cfg["max_delay"], loop=asyncio.get_event_loop())

    # prepare node ids and keys
    ids = [f"R{i}" for i in range(n)]
    privs = {nid: secrets.token_hex(16) for nid in ids}

    # instantiate replicas
    replicas = {}
    for i, nid in enumerate(ids):
        is_byz = i in byz
        is_abc = i in abc
        r = Replica(node_id=nid, privkey=privs[nid], all_ids=ids, network=net, f=f, is_byzantine=is_byz, is_abc=is_abc)
        replicas[nid] = r

    # learners: one fast, one safe
    # fast learner assumes smaller threshold
    fast_learner = Learner(name="fast", network=net, subscribe_to=ids, q_threshold_fast=4, q_threshold_commit=6)
    safe_learner = Learner(name="safe", network=net, subscribe_to=ids, q_threshold_fast=999, q_threshold_commit=2*f+1)

    # start replicas and learners
    tasks = []
    for r in replicas.values():
        tasks.append(asyncio.create_task(r.start()))
    tasks.append(asyncio.create_task(fast_learner.run()))
    tasks.append(asyncio.create_task(safe_learner.run()))

    # run simulation for some seconds
    await asyncio.sleep(6)

    # stop replicas
    for r in replicas.values():
        await r.stop()
    for t in tasks:
        t.cancel()

    print("Simulation finished.")
    print("Fast learner commits:", fast_learner.committed)
    print("Safe learner commits:", safe_learner.committed)

if __name__ == "__main__":
    asyncio.run(main())
