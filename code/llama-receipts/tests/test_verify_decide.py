from receipts.verify import Thresholds, decide

OK_STRUCT = (True, "ok")


def _summary(**over):
    base = {
        "n": 48,
        "token_match_rate": 1.0,
        "logits_hash_match_rate": 1.0,
        "n_claimed_truncated": 0,
        "mean_abs_dlogprob": 0.0,
        "max_abs_dlogprob": 0.0,
        "mismatch_gap_max": None,
        "mean_gap_all": 0.0,
        "n_hard_mismatch": 0,
    }
    base.update(over)
    return base


def test_bit_exact_accepts():
    assert decide(True, True, OK_STRUCT, _summary(), Thresholds()) == ("accept", "bit-exact replay")


def test_identical_logits_with_any_mismatch_is_sampler_tamper():
    s = _summary(token_match_rate=47 / 48, mismatch_gap_max=0.02, mean_gap_all=0.0004)
    verdict, reason = decide(True, True, OK_STRUCT, s, Thresholds())
    assert verdict == "reject" and "sampler disagrees" in reason


def test_drift_regime_tolerates_small_gaps():
    s = _summary(logits_hash_match_rate=0.0, token_match_rate=0.9, mismatch_gap_max=0.1, mean_gap_all=0.01,
                 mean_abs_dlogprob=0.05)
    assert decide(True, True, OK_STRUCT, s, Thresholds()) == ("accept", "within backend drift")


def test_drift_regime_rejects_large_gap():
    s = _summary(logits_hash_match_rate=0.0, token_match_rate=0.9, mismatch_gap_max=0.6, mean_gap_all=0.01)
    verdict, reason = decide(True, True, OK_STRUCT, s, Thresholds())
    assert verdict == "reject" and "CDF mass" in reason


def test_truncated_claim_rejects_in_any_regime():
    s = _summary(n_claimed_truncated=1)
    assert decide(True, True, OK_STRUCT, s, Thresholds())[0] == "reject"


def test_signature_structure_and_model_come_first():
    assert decide(False, True, OK_STRUCT, _summary(), Thresholds()) == ("reject", "signature")
    assert decide(True, True, (False, "bad"), _summary(), Thresholds())[1].startswith("malformed")
    assert decide(True, False, OK_STRUCT, _summary(), Thresholds()) == ("reject", "model hash mismatch")
