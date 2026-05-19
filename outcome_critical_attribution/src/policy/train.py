"""Training the logistic context policy.

Implements the loss from the thesis:

    L = BCE(q_theta, z)  +  lambda * Cost(X*)  +  gamma * KL(q_theta || p_phi)

* `z`        -- hard support-graph labels.
* `Cost`     -- expected retained tokens (a sparsity / budget pressure).
* `p_phi`    -- the attribution prior (soft labels), used as a KL anchor.

Optimized with plain batch gradient descent so the prototype has zero
third-party dependencies.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from policy.dataset import TrainingExample
from policy.model import FEATURE_DIM, LogisticContextPolicy, _sigmoid, featurize


@dataclass
class TrainConfig:
    epochs: int = 300
    lr: float = 0.3
    cost_lambda: float = 0.02
    kl_gamma: float = 0.1
    l2: float = 1e-4
    max_tokens: int = 64


def _example_rows(
    ex: TrainingExample, max_tokens: int
) -> list[tuple[list[float], int, float, int]]:
    """Flatten one example into (features, hard_label, soft_label, tokens)."""
    atoms = ex.trajectory_atoms
    n = max(1, len(atoms))
    rows = []
    for i, atom in enumerate(atoms):
        feats = featurize(atom, i / n, max_tokens)
        z = ex.labels.get(atom.id, 0)
        p = ex.soft_labels.get(atom.id, 0.0)
        rows.append((feats, z, p, atom.token_count))
    return rows


def train_policy(
    examples: list[TrainingExample],
    config: TrainConfig | None = None,
) -> LogisticContextPolicy:
    """Fit a LogisticContextPolicy on training examples; return the model."""
    config = config or TrainConfig()
    rows: list[tuple[list[float], int, float, int]] = []
    for ex in examples:
        rows.extend(_example_rows(ex, config.max_tokens))
    if not rows:
        return LogisticContextPolicy(max_tokens=config.max_tokens)

    weights = [0.0] * FEATURE_DIM
    max_token = max(r[3] for r in rows) or 1

    for _ in range(config.epochs):
        grad = [0.0] * FEATURE_DIM
        for feats, z, p, tokens in rows:
            logit = sum(w * f for w, f in zip(weights, feats, strict=True))
            q = _sigmoid(logit)
            # d/dlogit of BCE(q, z) is (q - z).
            err = q - z
            # KL(q || p) pull toward the attribution prior.
            kl_term = config.kl_gamma * (q - p)
            # Cost pressure: each retained token costs lambda.
            cost_term = config.cost_lambda * (tokens / max_token)
            # cost gradient wrt logit is cost_term * q * (1 - q).
            d_logit = err + kl_term + cost_term * q * (1.0 - q)
            for j, f in enumerate(feats):
                grad[j] += d_logit * f
        m = len(rows)
        for j in range(FEATURE_DIM):
            g = grad[j] / m + config.l2 * weights[j]
            weights[j] -= config.lr * g

    return LogisticContextPolicy(weights=weights, max_tokens=config.max_tokens)


def policy_loss(
    policy: LogisticContextPolicy,
    examples: list[TrainingExample],
    config: TrainConfig | None = None,
) -> dict[str, float]:
    """Report the decomposed loss for inspection / regression tests."""
    config = config or TrainConfig()
    bce = cost = kl = 0.0
    count = 0
    for ex in examples:
        for feats, z, p, tokens in _example_rows(ex, config.max_tokens):
            logit = sum(w * f for w, f in zip(policy.weights, feats, strict=True))
            q = _sigmoid(logit)
            eps = 1e-9
            bce += -(z * math.log(q + eps) + (1 - z) * math.log(1 - q + eps))
            cost += config.cost_lambda * q * tokens
            kl += config.kl_gamma * (
                q * math.log((q + eps) / (p + eps))
                + (1 - q) * math.log((1 - q + eps) / (1 - p + eps))
            )
            count += 1
    count = max(1, count)
    return {
        "bce": bce / count,
        "cost": cost / count,
        "kl": kl / count,
        "total": (bce + cost + kl) / count,
    }
