import math


class RunningStats:
    """Tracks an exponential moving average and variance over a stream of readings."""

    def __init__(self, span: int = 20, min_samples: int = 5):
        self.alpha: float = 2.0 / (span + 1.0)
        self.min_samples: int = min_samples
        self.mean: float = 0.0
        self.var: float = 0.0
        self.count: int = 0

    def update(self, value: float) -> tuple[float, float]:
        self.count += 1
        if self.count == 1:
            self.mean = value
            return self.mean, 0.0
        delta = value - self.mean
        self.mean += self.alpha * delta
        self.var = (1.0 - self.alpha) * (self.var + self.alpha * (delta**2))
        deviation = math.sqrt(self.var) if self.count >= self.min_samples else 0.0
        return self.mean, deviation
