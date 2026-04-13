import math
from collections import Counter

TIER_RELEVANCE = {1: 3, 2: 2, 3: 1, 0: 0, None: 0}

def compute_ndcg(results, k=10):
    """
    NDCG@K — 以 Tier 作為 relevance score (T1=3, T2=2, T3=1, Mismatch=0)
    Ideal DCG 假設最好的排序為所有 Tier-1 在最前面。
    """
    top_k = results[:k]
    gains = [TIER_RELEVANCE.get(p["tier"], 0) for p in top_k]

    dcg = sum(g / math.log2(i + 2) for i, g in enumerate(gains))

    # Ideal DCG: sort all available relevance scores descending
    all_gains = sorted([TIER_RELEVANCE.get(p["tier"], 0) for p in results], reverse=True)
    idcg = sum(g / math.log2(i + 2) for i, g in enumerate(all_gains[:k]))

    return round(dcg / idcg, 4) if idcg > 0 else 0.0


def compute_recall_stats(results, k_list=None):
    """
    計算召回率、T3 鬆散率、誤判率與 Tier 分佈。
    - relevance_rate: 全部結果中 T1+T2 佔比（有效召回）
    - tier3_rate:     全部結果中 T3 佔比（鬆散相關）
    - mismatch_rate:  全部結果中 T0/Miss 佔比（完全不相關）
    三者加總 = 1.0
    """
    total = len(results)
    tier_counts = Counter(p["tier"] for p in results)

    t1 = tier_counts.get(1, 0)
    t2 = tier_counts.get(2, 0)
    t3 = tier_counts.get(3, 0)
    miss = tier_counts.get(0, 0) + tier_counts.get(None, 0)

    stats = {
        "relevance_rate": round((t1 + t2) / total, 4) if total else 0.0,
        "tier3_rate":     round(t3 / total, 4)         if total else 0.0,
        "mismatch_rate":  round(miss / total, 4)        if total else 0.0,
        "tier_breakdown": {
            "tier1": t1, "tier2": t2, "tier3": t3,
            "mismatch": miss, "total": total,
        },
    }
    return stats


def compute_category_distribution(results, top_n=10):
    """
    計算回傳商品中各 main_cat_key 的分佈比例（前 top_n 個分類）
    """
    total = len(results)
    if not total:
        return []

    counter = Counter(p.get("main_cat_key") or "未知" for p in results)
    most_common = counter.most_common(top_n)

    return [
        {
            "cat_key": cat,
            "count": count,
            "percentage": round(count / total * 100, 1)
        }
        for cat, count in most_common
    ]


def compute_rank_delta(stage_results, prod_results):
    """
    對每個 product_id 計算 Stage rank - Prod rank (正數=Stage 比 Prod 更前面)
    回傳 dict: { product_id: delta }
    """
    prod_rank_map = {str(p["id"]): p["rank"] for p in prod_results}
    stage_rank_map = {str(p["id"]): p["rank"] for p in stage_results}

    deltas = {}
    for pid, stage_rank in stage_rank_map.items():
        if pid in prod_rank_map:
            # delta > 0 = stage 排更前面（改善）
            deltas[pid] = prod_rank_map[pid] - stage_rank

    return deltas
