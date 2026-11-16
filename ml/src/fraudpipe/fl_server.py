"""
FraudShield AI - Federated Learning Server
==========================================

Central server that orchestrates federated learning rounds:
  1. Sends global model weights to clients
  2. Collects client weight updates
  3. Aggregates using Federated Averaging (FedAvg)
  4. Evaluates global model on held-out test data
  5. Saves the final global model

Usage:
    python -m fraudpipe.fl_server --rounds 10 --clients 3 --out ml/models/federated
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import joblib
import numpy as np

SRC_DIR = Path(__file__).resolve().parent
import sys
sys.path.insert(0, str(SRC_DIR))

from fraudpipe.fed_avg import (
    FLConfig, ClientUpdate, model_to_weights, weights_to_model,
    aggregate_fedavg, aggregate_weighted_fedavg, evaluate_model, create_mlp,
)
from preprocessing import load_raw_dataset, stratified_split, fit_scaler, apply_scaler, build_feature_matrix  # noqa: E402


class FLServer:
    """Central federated learning server."""

    def __init__(self, config: FLConfig | None = None,
                 test_data_path: str | Path | None = None):
        self.config = config or FLConfig()
        self.global_model = None
        self.round = 0
        self.clients: dict[str, ClientUpdate] = {}
        self.history: list[dict] = []

        # Load held-out test data for global evaluation
        self.X_test = None
        self.y_test = None
        if test_data_path:
            self._load_test_data(test_data_path)

    def _load_test_data(self, data_path: str | Path) -> None:
        df = load_raw_dataset(data_path)
        _, test_df, _ = stratified_split(df, test_size=0.2, val_size=0.0)
        scaler = fit_scaler(test_df)  # scaler fit on test only for eval purposes
        test_scaled = apply_scaler(test_df, scaler)
        self.X_test, self.y_test = build_feature_matrix(test_scaled)
        print(f"[server] loaded {len(self.X_test)} test samples, "
              f"input_dim={self.X_test.shape[1]}")

    def initialize_global_model(self) -> None:
        """Create the initial global model."""
        if self.X_test is None:
            raise RuntimeError("Test data must be loaded before initializing model")
        input_dim = self.X_test.shape[1]
        self.global_model = create_mlp(input_dim, self.config)
        # Fit once on a small subset to initialize weights properly
        # (MLP needs at least one fit to create coefs_/intercepts_)
        from sklearn.datasets import make_classification
        X_dummy, y_dummy = make_classification(
            n_samples=100, n_features=input_dim, n_informative=input_dim // 2,
            n_redundant=input_dim // 4, random_state=self.config.random_state
        )
        self.global_model.fit(X_dummy, y_dummy)
        print(f"[server] global model initialized (round 0)")

    def aggregate_updates(self, updates: list[ClientUpdate]) -> None:
        """Aggregate client updates using the configured aggregation method."""
        if not updates:
            raise ValueError("No client updates to aggregate")

        if self.config.aggregation == "weighted_fedavg":
            self.global_model = aggregate_weighted_fedavg(updates, self.global_model)
        else:
            self.global_model = aggregate_fedavg(updates, self.global_model)

        self.round += 1

    def evaluate_global(self) -> dict[str, float]:
        """Evaluate the global model on held-out test data."""
        if self.global_model is None or self.X_test is None:
            raise RuntimeError("Model or test data not initialized")
        metrics = evaluate_model(self.global_model, self.X_test, self.y_test)
        print(f"[server] round {self.round} global eval: "
              f"PR-AUC={metrics['pr_auc']:.4f} "
              f"ROC-AUC={metrics['roc_auc']:.4f} "
              f"F1={metrics['f1']:.4f}")
        self.history.append({"round": self.round, **metrics})
        return metrics

    def save_model(self, out_path: str | Path) -> None:
        """Save the global federated model."""
        out_path = Path(out_path)
        out_path.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.global_model, out_path / "global_model.joblib")
        config_path = out_path / "fl_config.json"
        with open(config_path, "w") as f:
            json.dump(asdict(self.config), f, indent=2)
        history_path = out_path / "training_history.json"
        with open(history_path, "w") as f:
            json.dump(self.history, f, indent=2)
        print(f"[server] global model + config + history saved -> {out_path}")

    def get_global_weights(self) -> list[np.ndarray]:
        """Return current global model weights for distribution to clients."""
        if self.global_model is None:
            raise RuntimeError("Global model not initialized")
        return model_to_weights(self.global_model)


def main():
    ap = argparse.ArgumentParser(description="FraudShield AI Federated Learning Server")
    ap.add_argument("--rounds", type=int, default=10, help="Number of federated rounds")
    ap.add_argument("--clients", type=int, default=3, help="Expected number of clients")
    ap.add_argument("--min-clients", type=int, default=2, help="Min clients per round")
    ap.add_argument("--data", type=Path, help="Path to CSV data for test/eval split")
    ap.add_argument("--out", type=Path, default=Path("ml/models/federated"),
                    help="Output directory for global model")
    ap.add_argument("--aggregation", choices=["fedavg", "weighted_fedavg"],
                    default="fedavg", help="Aggregation method")
    a = ap.parse_args()

    config = FLConfig(
        n_rounds=a.rounds,
        n_clients=a.clients,
        min_clients_per_round=a.min_clients,
        aggregation=a.aggregation,
    )

    server = FLServer(config=config, test_data_path=a.data)
    server.initialize_global_model()

    print(f"\n[server] Federated learning ready: {a.rounds} rounds, "
          f"{a.clients} clients, aggregation={a.aggregation}")
    print(f"[server] Waiting for client updates...")
    print(f"[server] Each client should submit weight updates for each round.")
    print(f"[server] After all rounds, run with --collect to aggregate and save.")

    # For demo: if data is provided, simulate clients by splitting data
    if a.data:
        print(f"\n[server] Running simulation with data from {a.data}")
        _run_simulation(server, a.data, a.clients, a.rounds, a.out)


def _run_simulation(server: FLServer, data_path: Path, n_clients: int, n_rounds: int, out_path: Path) -> None:
    """Simulate federated learning by splitting data among clients."""
    import pandas as pd
    from sklearn.model_selection import train_test_split

    df = load_raw_dataset(data_path)
    # Split data among clients (non-IID simulation)
    client_dfs = np.array_split(df, n_clients)

    input_dim = server.X_test.shape[1]
    template_weights = model_to_weights(server.global_model)

    for rnd in range(1, n_rounds + 1):
        print(f"\n[server] Round {rnd}/{n_rounds}")
        updates = []

        for i, client_df in enumerate(client_dfs):
            # Save client data temporarily
            client_path = Path(f"/tmp/fl_client_{i}.csv") if os.name != "nt" else Path(f"C:\\temp\\fl_client_{i}.csv")
            client_path.parent.mkdir(parents=True, exist_ok=True)
            client_df.to_csv(client_path, index=False)

            from fraudpipe.fl_client import FLClient
            client = FLClient(client_id=f"client_{i}", config=server.config)
            client.load_data(client_path)
            client.initialize_model(template_weights)

            # Local training
            for _ in range(server.config.local_epochs):
                client.train_local()

            # Get update
            update = client.get_update(round_num=rnd)
            updates.append(update)

        # Aggregate
        server.aggregate_updates(updates)

        # Evaluate
        server.evaluate_global()

    server.save_model(out_path)


if __name__ == "__main__":
    main()