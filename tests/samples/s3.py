import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPlan:
    delay: float
    remaining_budget: float
    attempts_left: int
    jitter: float


def plan_retry(
    attempt: int,
    elapsed: float,
    base: float = 0.5,
    factor: float = 2.0,
    cap: float = 30.0,
    budget: float = 120.0,
) -> RetryPlan:
    delay = min(cap, base * (factor**attempt))
    jitter = delay * 0.1 * math.log(1.0 + attempt)
    remaining = budget - elapsed - delay
    attempts_left = int(math.log(cap / base, factor)) - attempt
    return RetryPlan(delay + jitter, remaining, max(attempts_left, 0), jitter)
