# utils.py
# Simple block, vote, QC definitions and simulated signatures (sha256 based)
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional, List

def now_ms():
    return int(time.time() * 1000)

def simple_sign(private_key: str, message: str) -> str:
    # Simulated signature: sha256(private_key || message)
    h = hashlib.sha256()
    h.update(private_key.encode())
    h.update(message.encode())
    return h.hexdigest()

@dataclass
class Block:
    height: int
    parent_id: Optional[str]
    proposer: str
    payload: str
    view: int
    id: str = field(init=False)
    justify_qc_id: Optional[str] = None  # QC id for parent or justification
    timestamp: int = field(default_factory=now_ms)

    def __post_init__(self):
        # id derived from content
        self.id = hashlib.sha256(f"{self.height}:{self.parent_id}:{self.proposer}:{self.payload}:{self.view}:{self.timestamp}".encode()).hexdigest()

@dataclass
class Vote:
    block_id: str
    voter: str
    view: int
    sig: str

@dataclass
class QC:
    block_id: str
    signer_ids: List[str]
    combined_sig: str  # simulated aggregate signature
    view: int

    def id(self):
        return hashlib.sha256(f"{self.block_id}:{','.join(self.signer_ids)}:{self.combined_sig}:{self.view}".encode()).hexdigest()

