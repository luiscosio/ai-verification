import hashlib

from receipts.merkle import leaf_hash, merkle_proof, merkle_root, node_hash, verify_proof


def test_empty_tree_is_hash_of_nothing():
    assert merkle_root([]) == hashlib.sha256(b"").digest()


def test_single_leaf_root_is_leaf_hash():
    assert merkle_root([b"a"]) == leaf_hash(b"a")


def test_two_leaves():
    assert merkle_root([b"a", b"b"]) == node_hash(leaf_hash(b"a"), leaf_hash(b"b"))


def test_odd_level_duplicates_last():
    a, b, c = leaf_hash(b"a"), leaf_hash(b"b"), leaf_hash(b"c")
    expected = node_hash(node_hash(a, b), node_hash(c, c))
    assert merkle_root([b"a", b"b", b"c"]) == expected


def test_proofs_verify_for_every_leaf():
    leaves = [f"leaf-{i}".encode() for i in range(7)]
    root = merkle_root(leaves)
    for i, leaf in enumerate(leaves):
        assert verify_proof(leaf, merkle_proof(leaves, i), root)


def test_tampered_leaf_fails():
    leaves = [f"leaf-{i}".encode() for i in range(5)]
    root = merkle_root(leaves)
    proof = merkle_proof(leaves, 2)
    assert not verify_proof(b"leaf-2x", proof, root)


def test_leaf_and_node_domains_differ():
    assert leaf_hash(b"xy") != node_hash(b"x", b"y")


def test_batch_proofs_match_single_proofs():
    from receipts.merkle import merkle_proof, merkle_proofs, merkle_root, verify_proof

    leaves = [bytes([i]) * 3 for i in range(11)]
    root = merkle_root(leaves)
    batch = merkle_proofs(leaves, [0, 5, 10])
    for i, path in batch.items():
        assert path == merkle_proof(leaves, i)
        assert verify_proof(leaves[i], path, root)
