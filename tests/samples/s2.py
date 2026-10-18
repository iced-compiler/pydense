import numpy as np
import pandas as pd


def inverse_variance_weights(features: pd.DataFrame, smoothing: float = 0.15) -> np.ndarray:
    """Blends the sample covariance with an identity prior and returns normalized inverse-variance weights."""
    if features.empty or len(features) < 3:
        raise ValueError("Need at least 3 rows of features")
    sample_cov = features.cov().values
    n_features = sample_cov.shape[0]
    prior = np.eye(n_features) * (np.trace(sample_cov) / n_features)
    blended = (1.0 - smoothing) * sample_cov + smoothing * prior
    scales = np.sqrt(np.diag(blended))
    raw_weights = [1.0 / s if s > 0.0 else 0.0 for s in scales]
    total = sum(raw_weights)
    return (
        np.array([w / total for w in raw_weights])
        if total > 0.0
        else np.ones(n_features) / n_features
    )
