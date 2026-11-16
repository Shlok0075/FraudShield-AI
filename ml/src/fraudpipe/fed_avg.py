"""
FraudShield AI - Federated Deep Learning (PART 8)
===================================================

Privacy-oriented distributed training architecture. Multiple clients (e.g.,
different banks or branches) train local models on their own data without
sharing raw transactions. A central server aggregates model updates using
Federated Averaging (FedAvg).

Components:
  - fed_avg.py        : Federated Averaging weight aggregation
  - fl_client.py      : Client that trains locally and sends weight updates
  - fl_server.py      : Server that orchestrates rounds and aggregates models

Usage:
    # Start server (runs N rounds, then saves global model)
    python -m fraudpipe.fl_server --rounds 10 --clients 3 --out ml/models/federated

    # Each client runs locally with its own data partition
    python -m fraudpipe.fl_client --client-id 0 --data client_0.csv --server-rounds 10
"""

from __future__ import annotations

import copy
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from sklearn.neural_network import MLPClassifier
from sklearn.metrics import average_precision_score, precision_score, recall_score, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split


@dataclass
class FLConfig:
    """Federated Learning configuration."""
    n_rounds: int = 10
    n_clients: int = 3
    local_epochs: int = 5
    local_batch_size: int = 32
    learning_rate: float = 0.01
    hidden_layer_sizes: tuple = (64, 32)
    random_state: int = 42
    min_clients_per_round: int = 2
    aggregation: str = "fedavg"  # "fedavg" or "weighted_fedavg"


@dataclass
class ClientUpdate:
    """A single client's model weight update."""
    client_id: str
    n_samples: int
    weights: list[np.ndarray]  # coefs + intercepts flattened
    metrics: dict[str, float]
    round: int


def model_to_weights(model: MLPClassifier) -> list[np.ndarray]:
    """Extract MLP weights and intercepts as a list of numpy arrays."""
    weights = []
    for coef in model.coefs_:
        weights.append(coef.copy())
    for intercept in model.intercepts_:
        weights.append(intercept.copy())
    return weights


def weights_to_model(template: MLPClassifier, weights: list[np.ndarray]) -> MLPClassifier:
    """Load weights into a template MLPClassifier model."""
    model = copy.deepcopy(template)
    n_coefs = len(model.coefs_)
    for i, coef in enumerate(model.coefs_):
        model.coefs_[i] = weights[i].copy()
    for i, intercept in enumerate(model.intercepts_):
        model.intercepts_[i] = weights[n_coefs + i].copy()
    return model


def aggregate_fedavg(updates: list[ClientUpdate], template: MLPClassifier) -> MLPClassifier:
    """Federated Averaging: weighted mean of client updates by n_samples."""
    total_samples = sum(u.n_samples for u in updates)
    n_coefs = len(template.coefs_)
    n_intercepts = len(template.intercepts_)

    # Initialize aggregated weights
    aggregated_coefs = [np.zeros_like(c) for c in template.coefs_]
    aggregated_intercepts = [np.zeros_like(i) for i in template.intercepts_]

    for update in updates:
        weight = update.n_samples / total_samples
        client_weights = update.weights
        for i in range(n_coefs):
            aggregated_coefs[i] += weight * client_weights[i]
        for i in range(n_intercepts):
            aggregated_intercepts[i] += weight * client_weights[n_coefs + i]

    # Build final model
    model = copy.deepcopy(template)
    for i, coef in enumerate(model.coefs_):
        model.coefs_[i] = aggregated_coefs[i]
    for i, intercept in enumerate(model.intercepts_):
        model.intercepts_[i] = aggregated_intercepts[i]
    return model


def aggregate_weighted_fedavg(updates: list[ClientUpdate], template: MLPClassifier) -> MLPClassifier:
    """Weighted FedAvg with additional weighting by client data quality (local PR-AUC)."""
    total_weight = 0.0
    n_coefs = len(template.coefs_)
    n_intercepts = len(template.intercepts_)

    aggregated_coefs = [np.zeros_like(c) for c in template.coefs_]
    aggregated_intercepts = [np.zeros_like(i) for i in template.intercepts_]

    for update in updates:
        # Combine sample count with local performance
        perf_weight = max(update.metrics.get("pr_auc", 0.5), 0.01)
        combined_weight = update.n_samples * perf_weight
        total_weight += combined_weight
        client_weights = update.weights
        for i in range(n_coefs):
            aggregated_coefs[i] += combined_weight * client_weights[i]
        for i in range(n_intercepts):
            aggregated_intercepts[i] += combined_weight * client_weights[n_coefs + i]

    if total_weight == 0:
        return aggregate_fedavg(updates, template)

    model = copy.deepcopy(template)
    for i, coef in enumerate(model.coefs_):
        model.coefs_[i] = aggregated_coefs[i] / total_weight
    for i, intercept in enumerate(model.intercepts_):
        model.intercepts_[i] = aggregated_intercepts[i] / total_weight
    return model


def evaluate_model(model: MLPClassifier, X: np.ndarray, y: np.ndarray) -> dict[str, float]:
    """Evaluate a model and return standard fraud-detection metrics."""
    proba = model.predict_proba(X)[:, 1]
    pred = (proba >= 0.5).astype(int)
    tn, fp, fn, tp = __import__("sklearn.metrics", fromlist=["confusion_matrix"]).confusion_matrix(y, pred).ravel()
    return {
        "precision": float(__import__("sklearn.metrics", fromlist=["precision_score"]).precision_score(y, pred, zero_division=0)),
        "recall": float(__import__("sklearn.metrics", fromlist=["recall_score"]).recall_score(y, pred, zero_division=0)),
        "f1": float(__import__("sklearn.metrics", fromlist=["f1_score"]).f1_score(y, pred, zero_division=0)),
        "roc_auc": float(__import__("sklearn.metrics", fromlist=["roc_auc_score"]).roc_auc_score(y, proba)),
        "pr_auc": float(__import__("sklearn.metrics", fromlist=["average_precision_score"]).average_precision_score(y, proba)),
        "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn),
    }


def create_mlp(input_dim: int, config: FLConfig) -> MLPClassifier:
    """Create a fresh MLPClassifier with the given configuration."""
    return MLPClassifier(
        hidden_layer_sizes=config.hidden_layer_sizes,
        learning_rate_init=config.learning_rate,
        max_iter=config.local_epochs,
        random_state=config.random_state,
        early_stopping=True,
        validation_fraction=0.1,
    )


__all__ = [
    "FLConfig", "ClientUpdate", "model_to_weights", "weights_to_model",
    "aggregate_fedavg", "aggregate_weighted_fedavg", "evaluate_model",
    "create_mlp",
]
