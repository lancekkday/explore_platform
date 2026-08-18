"""spec 4.1 — relevance_status_code 六碼解碼。

驗收條件 5:遇到非預期格式回 None,不猜值、不丟例外。
"""
import pytest

from src.domain.relevance import RELEVANCE_DIMS, decode_relevance


def test_dims_order_matches_spec():
    # 由左至右:可售/地點/類目/IP/主題/文本 (spec 4.1 表格)
    assert RELEVANCE_DIMS == ["sellable", "location", "category", "ip", "theme", "text"]


def test_decode_spec_example():
    # spec 內文範例:'000220'
    assert decode_relevance("000220") == {
        "sellable": 0, "location": 0, "category": 0, "ip": 2, "theme": 2, "text": 0,
    }


def test_decode_all_zero():
    assert decode_relevance("000000") == {d: 0 for d in RELEVANCE_DIMS}


def test_decode_observed_value_domain_not_boolean():
    # 已觀測值域含 0 與 2 — 解碼不得假設布林
    out = decode_relevance("222222")
    assert all(v == 2 for v in out.values())


@pytest.mark.parametrize("bad", [
    None,          # 缺值
    "",            # 空字串
    "00022",       # 5 碼
    "0002200",     # 7 碼
    "00022x",      # 非數字
    "０００２２０",  # 全形數字 (isdigit()=True 但 int() 可過 — 見實作註記)
    "00-220",      # 帶符號
])
def test_decode_malformed_returns_all_none(bad):
    out = decode_relevance(bad)
    assert set(out.keys()) == set(RELEVANCE_DIMS)
    assert all(v is None for v in out.values())


def test_decode_never_raises():
    # 驗收 5:不丟例外
    for weird in [123456, 1.5, ["0"] * 6, {"x": 1}, b"000220"]:
        out = decode_relevance(weird)  # type: ignore[arg-type]
        assert all(v is None for v in out.values())


def test_decode_is_pure():
    a = decode_relevance("000220")
    b = decode_relevance("000220")
    assert a == b and a is not b
