"""
Regression test for the AB cross-version match bug.

Root cause (introduced in commit ad45879, the original A/B feature): the v3 search
API returns prod_mid as an int for some test_exp versions and as a str for others.
The AB comparison built its match keys from the raw value, so 137689 (int, version A)
never equaled "137689" (str, version B) — every product showed "未出現" (0% cross-
match) even when it was present in both columns.

Fix: _normalize_mid() coerces every prod_mid to int before it is used as a match key,
in both _process_version (result rows fed to the frontend) and _compute_ab_comparison
(a_mids / b_mids + baseline mids).

Pure unit tests — no backend / cookie / network required:
    cd backend && ./venv/bin/python -m pytest tests/test_ab_mid_normalization.py -v
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from main import _normalize_mid
from ab_check import find_rank as ab_find_rank


# The exact data shape the v3 API returned for `esim`, v0 vs v1 (see investigation).
# Version A (test_exp=0): prod_mid is int.
A_RAW = [121004, 243815, 135627, 137689, 138273]
# Version B (test_exp=1): the SAME products, but prod_mid serialized as str.
B_RAW = ["132803", "121004", "243815", "135627", "137689"]


def test_normalize_mid_collapses_int_and_str():
    assert _normalize_mid(137689) == _normalize_mid("137689") == 137689


def test_normalize_mid_handles_missing_and_garbage():
    assert _normalize_mid(None) == 0
    assert _normalize_mid("") == 0
    assert _normalize_mid("abc") == 0
    assert _normalize_mid(0) == 0


def test_normalize_mid_handles_float_like_strings():
    """CSV / some API responses surface ids as float-like strings; coerce them
    instead of dropping to 0 (consistent with baseline_service._safe_int)."""
    assert _normalize_mid("12345.0") == 12345
    assert _normalize_mid(12345.0) == 12345
    assert _normalize_mid("137689") == 137689


def test_cross_version_match_succeeds_after_normalization():
    """A#4 (137689, int) must be found in B, where it is the str '137689'."""
    a_mids = tuple(_normalize_mid(m) for m in A_RAW)
    b_mids = tuple(_normalize_mid(m) for m in B_RAW)

    assert ab_find_rank(a_mids[3], b_mids) == 5  # 137689 present in B at rank 5

    # Every A product that also exists in B is matched (4 of 5; 132803 is B-only).
    matched = sum(1 for m in a_mids if ab_find_rank(m, b_mids) is not None)
    assert matched == 4


def test_raw_mixed_types_match_nothing():
    """Guards the root cause: without normalization, mixed int/str keys match ZERO
    products. If this ever starts matching, the v3 API stopped returning mixed types
    and the normalization guarantee should be re-examined."""
    raw_matched = sum(1 for m in A_RAW if ab_find_rank(m, tuple(B_RAW)) is not None)
    assert raw_matched == 0  # int 137689 != str "137689"


def test_malformed_product_resolves_to_zero_sentinel():
    """A present product whose id fields are unusable must resolve to the 0 sentinel —
    this is the exact condition _process_version uses to emit an error log + surface a
    mid_warning, since real prod_mids are always non-zero positive integers."""
    # Neither prod_mid nor prod_oid usable -> 0 (flagged as anomaly).
    assert (_normalize_mid("N/A") or _normalize_mid(None)) == 0
    assert (_normalize_mid(None) or _normalize_mid("")) == 0
    # prod_mid missing/zero but prod_oid valid -> falls back, NOT an anomaly.
    assert (_normalize_mid(None) or _normalize_mid(243815)) == 243815
    assert (_normalize_mid("0") or _normalize_mid("243815")) == 243815


def test_same_version_comparison_masks_the_bug():
    """Why this went unnoticed: comparing a version against itself (A == B, e.g. the
    prod-vs-prod calibration round in SKILL.md) matches fine even with raw values,
    because both sides share the same type. This is the trap, captured as a test."""
    same = tuple(A_RAW)
    matched = sum(1 for m in A_RAW if ab_find_rank(m, same) is not None)
    assert matched == len(A_RAW)
