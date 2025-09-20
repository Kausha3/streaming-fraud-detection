#!/usr/bin/env python3
"""Train a sample FraudDetectionModel using synthetic features (no external deps)."""
from __future__ import annotations

import os
import random
from pathlib import Path
from typing import Dict, List

ROOT_DIR = Path(__file__).resolve().parent.parent
SRC_PATH = ROOT_DIR / "src"
if str(SRC_PATH) not in os.sys.path:
    os.sys.path.append(str(SRC_PATH))

from models.fraud_model import FraudDetectionModel, ModelArtifacts  # type: ignore  # noqa: E402

FEATURE_NAMES: List[str] = [
    "amount",
    "hour_of_day",
    "day_of_week",
    "is_weekend",
    "tx_count_1min",
    "tx_count_5min",
    "amount_sum_1min",
    "amount_sum_5min",
    "location_change",
    "is_foreign",
    "new_device",
    "device_count",
    "amount_deviation",
    "merchant_frequency",
    "card_not_present",
    "rapid_succession",
    "duplicate_amount",
]


def synthesize(rows: int = 6000) -> Dict[str, List[List[float]]]:
    normal_rows: List[List[float]] = []
    fraud_rows: List[List[float]] = []

    for _ in range(rows):
        fraud = random.random() < 0.15
        amount = random.gauss(250 if not fraud else 2500, 120 if not fraud else 800)
        hour = random.randint(0, 23)
        dow = random.randint(0, 6)
        weekend = 1 if dow >= 5 else 0
        tx1 = random.randint(0, 3 if not fraud else 8)
        tx5 = random.randint(1, 8 if not fraud else 20)
        amt1 = abs(amount) * (tx1 + 1) * random.uniform(0.8, 1.2)
        amt5 = abs(amount) * (tx5 + 1) * random.uniform(0.8, 1.3)
        location_change = 1 if random.random() < (0.05 if not fraud else 0.6) else 0
        foreign = 1 if random.random() < (0.1 if not fraud else 0.8) else 0
        new_device = 1 if random.random() < (0.1 if not fraud else 0.7) else 0
        device_count = random.randint(1, 4 if not fraud else 12)
        amount_dev = random.gauss(1 if not fraud else 5, 0.5 if not fraud else 1.3)
        merchant_freq = random.uniform(0.3, 0.8) if not fraud else random.uniform(0.0, 0.3)
        card_not_present = 1 if random.random() < (0.2 if not fraud else 0.85) else 0
        rapid = 1 if random.random() < (0.1 if not fraud else 0.7) else 0
        duplicate = 1 if random.random() < (0.05 if not fraud else 0.35) else 0

        row = [
            float(amount),
            float(hour),
            float(dow),
            float(weekend),
            float(tx1),
            float(tx5),
            float(amt1),
            float(amt5),
            float(location_change),
            float(foreign),
            float(new_device),
            float(device_count),
            float(amount_dev),
            float(merchant_freq),
            float(card_not_present),
            float(rapid),
            float(duplicate),
        ]

        if fraud:
            fraud_rows.append(row)
        else:
            normal_rows.append(row)

    X = normal_rows + fraud_rows
    y = [0] * len(normal_rows) + [1] * len(fraud_rows)

    combined = list(zip(X, y))
    random.shuffle(combined)
    X_shuffled, y_shuffled = zip(*combined)
    return {"X": [list(row) for row in X_shuffled], "y": list(y_shuffled)}


def main() -> None:
    random.seed(42)
    dataset = synthesize(rows=6000)
    artifacts = ModelArtifacts(directory=ROOT_DIR / "artifacts")

    model = FraudDetectionModel(artifacts=artifacts)
    model.train(dataset["X"], dataset["y"])

    reloaded = FraudDetectionModel(artifacts=artifacts)
    reloaded.load_models()

    sample = dict(zip(FEATURE_NAMES, dataset["X"][0]))
    prediction = reloaded.predict_with_explanation(sample)
    print("Sample prediction:", prediction)


if __name__ == "__main__":
    main()
