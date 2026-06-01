from collections import Counter


def build_step_frequencies(orders_map: dict) -> dict:
    """Count how many orders contain each unique step."""
    counter: Counter = Counter()
    for order in orders_map.values():
        raw = order["steps"]
        for step in set(raw.tolist() if hasattr(raw, "tolist") else (raw or [])):
            counter[step] += 1
    return dict(counter.most_common())


def get_top_sequences(orders_map: dict, top_n: int = 20) -> list[dict]:
    """Return the top N most common step sequences across all orders."""
    seq_counter: Counter = Counter()
    for order in orders_map.values():
        raw = order["steps"]
        steps = raw.tolist() if hasattr(raw, "tolist") else list(raw or [])
        key = " → ".join(str(s) for s in steps)
        if key:
            seq_counter[key] += 1

    result = []
    for seq_str, count in seq_counter.most_common(top_n):
        result.append({"sequence": seq_str.split(" → "), "count": count})
    return result
