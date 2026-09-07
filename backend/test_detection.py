#!/usr/bin/env python3
"""Test leggeri (senza modelli) per catalogo, residuo e rilevamento overlap.

Avvio:  .venv/bin/python backend/test_detection.py
(Non carica torch/SpeechBrain: usa solo la logica pura del catalogo.)
"""
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import server

rng = np.random.default_rng(7)
_DIM = 192


def make_embed(seed=None):
    e = (rng if seed is None else np.random.default_rng(seed)).standard_normal(_DIM)
    return e / np.linalg.norm(e)


def orthogonal_pair():
    e1 = make_embed()
    e2 = make_embed()
    e2 = e2 - np.dot(e2, e1) * e1
    e2 /= np.linalg.norm(e2)
    return e1, e2


def test_match_empty_catalog():
    cat = server.SpeakerCatalog()
    best, cos = cat.match(make_embed())
    assert best is None and cos == -1.0


def test_match_then_labels():
    cat = server.SpeakerCatalog()
    e1, e2 = orthogonal_pair()
    l1 = cat.add(e1)
    l2 = cat.add(e2)
    assert (l1, l2) == ("voce1", "voce2")
    best, cos = cat.match(e1)
    assert best == "voce1" and cos > 0.99


def test_update_keeps_identity():
    cat = server.SpeakerCatalog()
    e1, e2 = orthogonal_pair()
    cat.add(e1)
    cat.update("voce1", 0.9 * e1 + 0.1 * e2)
    best, _ = cat.match(e1)
    assert best == "voce1"


def test_single_voice_no_overlap():
    cat = server.SpeakerCatalog()
    cat.add(make_embed())
    assert server.detect_overlap(cat, cat.by_label["voce1"]["embed"]) is None


def test_balanced_mix_overlap():
    cat = server.SpeakerCatalog()
    e1, e2 = orthogonal_pair()
    cat.add(e1)
    cat.add(e2)
    mix = 0.5 * e1 + 0.5 * e2
    mix /= np.linalg.norm(mix)
    ov = server.detect_overlap(cat, mix)
    assert ov is not None and set(ov) == {"voce1", "voce2"}


def test_unbalanced_mix_overlap_via_residual():
    cat = server.SpeakerCatalog()
    e1, e2 = orthogonal_pair()
    cat.add(e1)
    cat.add(e2)
    mix = 0.8 * e1 + 0.2 * e2
    mix /= np.linalg.norm(mix)
    assert server.detect_overlap(cat, mix) == ("voce1", "voce2")


def test_weak_second_voice_no_overlap():
    cat = server.SpeakerCatalog()
    e1, e2 = orthogonal_pair()
    cat.add(e1)
    cat.add(e2)
    single = 0.95 * e1 + 0.05 * e2
    single /= np.linalg.norm(single)
    assert server.detect_overlap(cat, single) is None


def test_residual_top_excludes_dominant():
    cat = server.SpeakerCatalog()
    e1, e2 = orthogonal_pair()
    cat.add(e1)
    cat.add(e2)
    rb, rc, rn = cat.residual_top(e1, "voce1")
    assert rn < server.RESIDUAL_NORM_MIN  # direzione = rumore
    rb2, rc2, _ = cat.residual_top(0.8 * e1 + 0.2 * e2, "voce1")
    assert rb2 == "voce2" and rc2 > 0.9


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok  {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} test superati")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)