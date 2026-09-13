import numpy as np

from receipts.sampler import (
    SamplerConfig,
    cdf_interval,
    draw_gap,
    log_softmax,
    logprob_of,
    sample,
    sampling_distribution,
    uniform_at,
)


def test_uniform_is_deterministic_and_in_range():
    a = uniform_at(42, 7)
    assert a == uniform_at(42, 7)
    assert 0.0 <= a < 1.0
    assert uniform_at(42, 8) != a
    assert uniform_at(43, 7) != a


def test_greedy_is_argmax_with_id_tiebreak():
    logits = np.array([1.0, 3.0, 3.0, 0.5], dtype=np.float32)
    res = sample(logits, SamplerConfig(temperature=0.0), position=0)
    assert res.token == 1
    assert res.u is None


def test_same_inputs_same_token():
    rng = np.random.default_rng(0)
    logits = rng.normal(size=1000).astype(np.float32)
    cfg = SamplerConfig(temperature=0.8, top_k=50, top_p=0.9, seed=123)
    a = sample(logits, cfg, position=5)
    b = sample(logits, cfg, position=5)
    assert a.token == b.token and a.u == b.u


def test_top_k_and_top_p_truncate():
    logits = np.array([10.0, 9.0, 8.0, 0.0, -5.0], dtype=np.float32)
    ids, probs = sampling_distribution(logits, SamplerConfig(temperature=1.0, top_k=2, top_p=1.0))
    assert list(ids) == [0, 1] and abs(probs.sum() - 1) < 1e-12
    ids, probs = sampling_distribution(logits, SamplerConfig(temperature=1.0, top_k=0, top_p=0.5))
    assert list(ids) == [0]


def test_logprob_of_truncated_token_is_minus_inf():
    logits = np.array([10.0, 9.0, 8.0, 0.0], dtype=np.float32)
    cfg = SamplerConfig(temperature=1.0, top_k=2, top_p=1.0)
    assert logprob_of(logits, cfg, 3) == float("-inf")
    assert logprob_of(logits, cfg, 0) < 0.0


def test_sampled_token_matches_inverse_cdf():
    logits = np.array([2.0, 1.0, 0.0], dtype=np.float32)
    cfg = SamplerConfig(temperature=1.0, top_k=0, top_p=1.0, seed=9)
    res = sample(logits, cfg, position=3)
    ids, probs = sampling_distribution(logits, cfg)
    cum = np.cumsum(probs)
    expected = ids[int(np.searchsorted(cum, res.u, side="right"))]
    assert res.token == int(expected)
    assert res.boundary_distance is not None and res.boundary_distance >= 0


def test_draw_gap_is_zero_for_the_sampled_token_and_positive_otherwise():
    logits = np.array([2.0, 1.0, 0.0], dtype=np.float32)
    cfg = SamplerConfig(temperature=1.0, top_k=0, top_p=1.0, seed=5)
    res = sample(logits, cfg, position=1)
    assert draw_gap(logits, cfg, res.token, res.u) == 0.0
    other = next(t for t in range(3) if t != res.token)
    gap = draw_gap(logits, cfg, other, res.u)
    assert gap is not None and gap > 0.0
    lo, hi = cdf_interval(logits, cfg, other)
    assert 0.0 <= lo < hi <= 1.0 + 1e-12
    assert draw_gap(logits, SamplerConfig(temperature=1.0, top_k=1, top_p=1.0), 2, 0.5) is None


def test_log_softmax_sums_to_one():
    x = np.array([0.1, -2.0, 5.0], dtype=np.float32)
    assert abs(np.exp(log_softmax(x)).sum() - 1.0) < 1e-12
