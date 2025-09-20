#!/usr/bin/env python3
"""Create dummy model artifacts for testing."""
import json
import pickle
from pathlib import Path

import numpy as np
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import IsolationForest
import xgboost as xgb

# Create artifacts directory if it doesn't exist
artifacts_dir = Path("artifacts")
artifacts_dir.mkdir(exist_ok=True)

# Generate dummy training data
np.random.seed(42)
n_samples = 1000
n_features = 15  # Based on feature_engineering.py feature count

# Create synthetic training data
X_train = np.random.randn(n_samples, n_features)
y_train = np.random.randint(0, 2, n_samples)

# Train and save StandardScaler
scaler = StandardScaler()
scaler.fit(X_train)
with open(artifacts_dir / "scaler.pkl", "wb") as f:
    pickle.dump(scaler, f)
print("✓ Scaler saved")

# Train and save IsolationForest
iso_forest = IsolationForest(contamination=0.1, random_state=42)
iso_forest.fit(X_train)
with open(artifacts_dir / "isolation_forest.pkl", "wb") as f:
    pickle.dump(iso_forest, f)
print("✓ Isolation Forest saved")

# Train and save XGBoost model
dtrain = xgb.DMatrix(X_train, label=y_train)
params = {
    'max_depth': 3,
    'eta': 0.1,
    'objective': 'binary:logistic',
    'eval_metric': 'logloss'
}
bst = xgb.train(params, dtrain, num_boost_round=100)
bst.save_model(str(artifacts_dir / "xgb.json"))
print("✓ XGBoost model saved")

print("\nModel artifacts created successfully!")
print(f"Location: {artifacts_dir.absolute()}")