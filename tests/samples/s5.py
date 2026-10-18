def with_multiplier(scale: float = 1.0):
    def decorator(func):
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs) * scale

        return wrapper

    return decorator


@with_multiplier(100.0)
def score_pipeline(
    base_scores: list[float], *bonus_lists: list[float], floor: float = 0.0, **weights: float
) -> float:
    combined = [*base_scores]
    for blist in bonus_lists:
        combined = [*combined, *blist]
    clamped = [x if x > floor else floor for x in combined]
    w_sum = sum(weights.values()) if weights else 1.0
    return (sum(clamped) / len(clamped)) * w_sum if clamped else 0.0
