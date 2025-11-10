# core/utils.py
import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional, List, Tuple

# --- Ed25519 via PyNaCl ---
from nacl import signing
from nacl.encoding import RawEncoder

def ed25519_keypair() -> Tuple[bytes, bytes]:
    sk = signing.SigningKey.generate()
    vk = sk.verify_key
    return (bytes(sk), bytes(vk))

def ed25519_sign(sk_bytes: bytes, msg: bytes) -> bytes:
    sk = signing.SigningKey(sk_bytes)
    signed = sk.sign(msg, encoder=RawEncoder)
    return signed.signature  # 64 bytes

def ed25519_verify(vk_bytes: bytes, msg: bytes, sig: bytes) -> bool:
    try:
        vk = signing.VerifyKey(vk_bytes)
        vk.verify(msg, sig, encoder=RawEncoder)
        return True
    except Exception:
        return False

def now_ms() -> int:
    return int(time.time() * 1000)

@dataclass
class Block:
    height: int
    parent_id: Optional[str]
    proposer: str
    payload: str
    view: int
    justify_qc_id: Optional[str] = None
    timestamp: int = field(default_factory=now_ms)
    id: str = field(init=False)

    def __post_init__(self):
        self.id = hashlib.sha256(
            f"{self.height}:{self.parent_id}:{self.proposer}:{self.payload}:{self.view}:{self.timestamp}".encode()
        ).hexdigest()

@dataclass
class Vote:
    block_id: str
    voter: str
    view: int
    sig: bytes  # Ed25519 signature

@dataclass
class QC:
    block_id: str
    signer_ids: List[str]
    signatures: List[bytes]  # list of Ed25519 signatures
    view: int

    def id(self) -> str:
        h = hashlib.sha256()
        h.update(self.block_id.encode())
        h.update(",".join(self.signer_ids).encode())
        h.update(str(self.view).encode())
        for s in self.signatures:
            h.update(s)
        return h.hexdigest()
