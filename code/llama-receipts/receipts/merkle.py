"""Binary SHA-256 Merkle tree with domain-separated leaves and audit paths.

Leaves are hashed as sha256(0x00 || data), internal nodes as
sha256(0x01 || left || right). An odd level duplicates its last node.
"""

from __future__ import annotations

import hashlib

LEAF_PREFIX = b"\x00"
NODE_PREFIX = b"\x01"


def _sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def leaf_hash(data: bytes) -> bytes:
    return _sha256(LEAF_PREFIX + data)


def node_hash(left: bytes, right: bytes) -> bytes:
    return _sha256(NODE_PREFIX + left + right)


def _levels(leaves: list[bytes]) -> list[list[bytes]]:
    """Return every level of the tree, leaves first, root last."""
    level = [leaf_hash(x) for x in leaves]
    levels = [level]
    while len(level) > 1:
        if len(level) % 2:
            level = level + [level[-1]]
        level = [node_hash(level[i], level[i + 1]) for i in range(0, len(level), 2)]
        levels.append(level)
    return levels


def merkle_root(leaves: list[bytes]) -> bytes:
    """Root of the tree over `leaves`. The empty tree hashes to sha256("")."""
    if not leaves:
        return _sha256(b"")
    return _levels(leaves)[-1][0]


def merkle_proof(leaves: list[bytes], index: int) -> list[tuple[str, bytes]]:
    """Audit path for leaf `index`: a list of (side, sibling_hash), bottom up.

    `side` is "L" when the sibling sits to the left of the running hash.
    """
    if not 0 <= index < len(leaves):
        raise IndexError(index)
    path: list[tuple[str, bytes]] = []
    i = index
    for level in _levels(leaves)[:-1]:
        padded = level + [level[-1]] if len(level) % 2 else level
        sibling = i ^ 1
        side = "L" if sibling < i else "R"
        path.append((side, padded[sibling]))
        i //= 2
    return path


def merkle_proofs(leaves: list[bytes], indices: list[int]) -> dict[int, list[tuple[str, bytes]]]:
    """Audit paths for many leaves, building the tree once."""
    levels = _levels(leaves)[:-1] if leaves else []
    out: dict[int, list[tuple[str, bytes]]] = {}
    for index in indices:
        if not 0 <= index < len(leaves):
            raise IndexError(index)
        path: list[tuple[str, bytes]] = []
        i = index
        for level in levels:
            padded = level + [level[-1]] if len(level) % 2 else level
            sibling = i ^ 1
            path.append(("L" if sibling < i else "R", padded[sibling]))
            i //= 2
        out[index] = path
    return out


def verify_proof(leaf_data: bytes, proof: list[tuple[str, bytes]], root: bytes) -> bool:
    """Check that `leaf_data` sits in the tree with `root` via `proof`."""
    running = leaf_hash(leaf_data)
    for side, sibling in proof:
        running = node_hash(sibling, running) if side == "L" else node_hash(running, sibling)
    return running == root
