"""
FraudShield AI - Federated Learning Client
==========================================

Each client trains a local MLP model on its own data partition and sends
weight updates to the central server. Raw transaction data never leaves
the client.

Usage:
    python -m fraudpipe.fl_client --client-id 0 --data client_data.csv \
        --rounds 10 --server-url http://localhost:8001
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SRC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC_DIR))

from fraudpipe.fed_avg import (
    FLConfig, ClientUpdate, model_to_weights, weights_to_model,
    evaluate_model, create_mlp,
)
from preprocessing import load_raw_dataset, stratified_split, fit_scaler, apply_scaler, build_feature_matrix  # noqa: E402


class FLClient:
    """A federated learning client that trains on local data."""

    def __init__(self, client_id: str, config: FLConfig | None = None):
        self.client_id = client_id
        self.config = config or FLConfig()
        self.model: MLPClassifier | None = None
        self.X_train: np.ndarray | None = None
        self.y_train: np.ndarray | None = None
        self.X_val: np.ndarray | None = None
        self.y_val: np.ndarray | None = None
        self.round = 0

    def load_data(self, data_path: str | Path, test_size: float = 0.2) -> None:
        """Load and preprocess local client data."""
        df = load_raw_dataset(data_path)
        train_df, test_df, _ = stratified_split(df, test_size=test_size, val_size=0.0)

        scaler = fit_scaler(train_df)
        train_scaled = apply_scaler(train_df, scaler)
        test_scaled = apply_scaler(test_df, scaler)

        self.X_train, self.y_train = build_feature_matrix(train_scaled)
        self.X_val, self.y_val = build_feature_matrix(test_scaled)

        input_dim = self.X_train.shape[1]
        self.model = create_mlp(input_dim, self.config)
        print(f"[client {self.client_id}] loaded {len(self.X_train)} train, "
              f"{len(self.X_val)} val samples, input_dim={input_dim}")

    def initialize_model(self, template_weights: list[np.ndarray] | None = None) -> None:
        """Initialize the local model, optionally from server weights."""
        if self.model is None:
            input_dim = self.X_train.shape[1]
            self.model = create_mlp(input_dim, self.config)
        # MLPClassifier needs at least one fit to create coefs_/intercepts_
        if not hasattr(self.model, "coefs_"):
            from sklearn.datasets import make_classification
            X_dummy, y_dummy = make_classification(
                n_samples=100, n_features=self.X_train.shape[1],
                n_informative=self.X_train.shape[1] // 2,
                n_redundant=self.X_train.shape[1] // 4,
                random_state=self.config.random_state
            )
            self.model.fit(X_dummy, y_dummy)
        if template_weights is not None:
            self.model = weights_to_model(self.model, template_weights)
        self.round = 0

    def train_local(self) -> dict[str, float]:
        """Train the local model for one round and return metrics."""
        if self.model is None:
            raise RuntimeError("Model not initialized")

        # Fit on local training data
        self.model.fit(self.X_train, self.y_train)
        self.round += 1

        # Evaluate on local validation data
        metrics = evaluate_model(self.model, self.X_val, self.y_val)
        print(f"[client {self.client_id}] round {self.round}: "
              f"PR-AUC={metrics['pr_auc']:.4f} "
              f"ROC-AUC={metrics['roc_auc']:.4f} "
              f"F1={metrics['f1']:.4f}")
        return metrics

    def get_update(self, round_num: int) -> ClientUpdate:
        """Create a weight update to send to the server."""
        if self.model is None:
            raise RuntimeError("Model not trained yet")
        weights = model_to_weights(self.model)
        metrics = evaluate_model(self.model, self.X_val, self.y_val) if self.X_val is not None else {}
        return ClientUpdate(
            client_id=self.client_id,
            n_samples=int(len(self.X_train)),
            weights=weights,
            metrics=metrics,
            round=round_num,
        )

    def apply_server_weights(self, weights: list[np.ndarray]) -> None:
        """Apply aggregated weights from the server to the local model."""
        if self.model is None:
            raise RuntimeError("Model not initialized")
        self.model = weights_to_model(self.model, weights)


def main():
    ap = argparse.ArgumentParser(description="FraudShield AI Federated Learning Client")
    ap.add_argument("--client-id", required=True, help="Unique client identifier")
    ap.add_argument("--data", required=True, type=Path, help="Path to client CSV data")
    ap.add_argument("--rounds", type=int, default=10, help="Number of federated rounds")
    ap.add_argument("--clients", type=int, default=3, help="Total number of clients")
    ap.add_argument("--local-epochs", type=int, default=5, help="Local training epochs per round")
    ap.add_argument("--no-federate", action="store_true",
                    help="Train locally only (no federation) for comparison")
    a = ap.parse_args()

    config = FLConfig(
        n_rounds=a.rounds,
        n_clients=a.clients,
        local_epochs=a.local_epochs,
    )

    client = FLClient(client_id=a.client_id, config=config)
    client.load_data(a.data)
    client.initialize_model()

    if a.no_federate:
        # Local-only training for comparison
        for r in range(a.rounds):
            client.train_local()
        final_metrics = evaluate_model(client.model, client.X_val, client.y_val)
        print(f"\n[client {a.client_id}] LOCAL-ONLY final: "
              f"PR-AUC={final_metrics['pr_auc']:.4f} "
              f"ROC-AUC={final_metrics['roc_auc']:.4f}")
        # Save local model
        import joblib
        joblib.dump(client.model, f"ml/models/local_{a.client_id}.joblib")
    else:
        print(f"\n[client {a.client_id}] Ready for federation ({a.rounds} rounds, "
              f"{a.clients} clients). Run fl_server to orchestrate.")
        # Save initial weights for server to collect
        import joblib
        update = client.get_update(round_num=0)
        update_path = Path(f"ml/models/client_{a.client_id}_update.json")
        update_path.parent.mkdir(parents=True, exist_ok=True)
        with open(update_path, "w") as f:
            json.dump({
                "client_id": update.client_id,
                "n_samples": update.n_samples,
                "weights": [w.tolist() for w in update.weights],
                "metrics": update.metrics,
                "round": update.round,
            }, f, indent=2)
        print(f"[client {a.client_id}] Initial weights saved -> {update_path}")


if __name__ == "__main__":
    main()