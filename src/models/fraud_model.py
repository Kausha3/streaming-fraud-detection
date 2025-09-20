"""Fraud detection ensemble model wrapper with graceful fallbacks."""
from __future__ import annotations

import json
import math
import pickle
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

# Optional heavy dependencies -------------------------------------------------
try:  # pragma: no cover - Real numpy if available
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover - fallback shim
    np = None  # type: ignore

try:  # pragma: no cover - Real sklearn if available
    from sklearn.ensemble import IsolationForest  # type: ignore
    from sklearn.preprocessing import StandardScaler  # type: ignore
except ImportError:  # pragma: no cover - lightweight fallbacks
    IsolationForest = None  # type: ignore
    StandardScaler = None  # type: ignore

try:  # pragma: no cover - Real SHAP if present
    import shap  # type: ignore
except ImportError:  # pragma: no cover
    shap = None  # type: ignore

try:  # pragma: no cover - Real XGBoost if available
    import xgboost as xgb  # type: ignore
except ImportError:  # pragma: no cover
    xgb = None  # type: ignore

# Lightweight fallbacks -------------------------------------------------------


class _SimpleStandardScaler:
    def __init__(self) -> None:
        self.means: List[float] = []
        self.scales: List[float] = []

    def fit(self, X: Sequence[Sequence[float]]) -> "_SimpleStandardScaler":
        cols = list(zip(*X)) if X else []
        self.means = [mean(col) if col else 0.0 for col in cols]
        self.scales = [pstdev(col) if len(col) > 1 else 1.0 for col in cols]
        self.scales = [scale if scale else 1.0 for scale in self.scales]
        return self

    def transform(self, X: Sequence[Sequence[float]]) -> List[List[float]]:
        if not self.means:
            raise RuntimeError("Scaler not fitted")
        transformed: List[List[float]] = []
        for row in X:
            transformed.append([
                (value - m) / s if s else 0.0
                for value, m, s in zip(row, self.means, self.scales)
            ])
        return transformed

    def fit_transform(self, X: Sequence[Sequence[float]]) -> List[List[float]]:
        self.fit(X)
        return self.transform(X)


class _SimpleIsolationForest:
    def __init__(self) -> None:
        self.means: List[float] = []
        self.scales: List[float] = []

    def fit(self, X: Sequence[Sequence[float]]) -> "_SimpleIsolationForest":
        cols = list(zip(*X)) if X else []
        self.means = [mean(col) if col else 0.0 for col in cols]
        self.scales = [pstdev(col) if len(col) > 1 else 1.0 for col in cols]
        self.scales = [scale if scale else 1.0 for scale in self.scales]
        return self

    def decision_function(self, X: Sequence[Sequence[float]]) -> List[float]:
        if not self.means:
            raise RuntimeError("Isolation forest not fitted")
        scores: List[float] = []
        for row in X:
            distance = 0.0
            for value, m, s in zip(row, self.means, self.scales):
                distance += abs(value - m) / s
            avg_distance = distance / len(self.means)
            scores.append(1.0 - avg_distance)
        return scores


class _SimpleXGBClassifier:
    def __init__(self, **_: float) -> None:
        self.weights: List[float] = []
        self.bias: float = 0.0
        self.feature_importances_: List[float] = []

    def fit(self, X: Sequence[Sequence[float]], y: Sequence[int]) -> "_SimpleXGBClassifier":
        if not X:
            return self
        cols = list(zip(*X))
        fraud_mask = [label == 1 for label in y]
        normal_mask = [not flag for flag in fraud_mask]

        fraud_means = [
            mean([col[i] for i in range(len(X)) if fraud_mask[i]]) if any(fraud_mask) else 0.0
            for col in cols
        ]
        normal_means = [
            mean([col[i] for i in range(len(X)) if normal_mask[i]]) if any(normal_mask) else 0.0
            for col in cols
        ]

        self.weights = [fraud - normal for fraud, normal in zip(fraud_means, normal_means)]
        self.bias = -sum(w * m for w, m in zip(self.weights, normal_means))

        importances = [abs(w) for w in self.weights]
        total = sum(importances) or 1.0
        self.feature_importances_ = [imp / total for imp in importances]
        return self

    def predict_proba(self, X: Sequence[Sequence[float]]) -> List[List[float]]:
        probs: List[List[float]] = []
        for row in X:
            score = sum(w * v for w, v in zip(self.weights, row)) + self.bias
            prob = 1.0 / (1.0 + math.exp(-score))
            probs.append([1.0 - prob, prob])
        return probs

    def save_model(self, path: Path | str) -> None:
        payload = {"weights": self.weights, "bias": self.bias}
        Path(path).write_text(json.dumps(payload))

    def load_model(self, path: Path | str) -> None:
        payload = json.loads(Path(path).read_text())
        self.weights = [float(x) for x in payload.get("weights", [])]
        self.bias = float(payload.get("bias", 0.0))
        importances = [abs(w) for w in self.weights]
        total = sum(importances) or 1.0
        self.feature_importances_ = [imp / total for imp in importances]


# Resolve implementations -----------------------------------------------------

if StandardScaler is None:  # pragma: no cover - fallback path
    StandardScaler = _SimpleStandardScaler  # type: ignore

if IsolationForest is None:  # pragma: no cover - fallback path
    IsolationForest = _SimpleIsolationForest  # type: ignore

if xgb is None:  # pragma: no cover - fallback xgboost shim
    class _XGBModule:  # type: ignore
        @staticmethod
        def XGBClassifier(**kwargs):
            return _SimpleXGBClassifier(**kwargs)

    xgb = _XGBModule()  # type: ignore


@dataclass
class ModelArtifacts:
    directory: Path = Path("artifacts")
    scaler_path: Path = Path("artifacts/scaler.pkl")
    isolation_forest_path: Path = Path("artifacts/isolation_forest.pkl")
    xgb_path: Path = Path("artifacts/xgb.json")

    def ensure(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)


class FraudDetectionModel:
    """Ensemble model providing predictions and explanations."""

    def __init__(self, artifacts: Optional[ModelArtifacts] = None) -> None:
        self.artifacts = artifacts or ModelArtifacts()
        self.scaler = StandardScaler()
        self.isolation_forest = IsolationForest()
        self.xgb_model = None
        self.explainer = None

    # ------------------------------------------------------------------
    def train(self, X: Sequence[Sequence[float]], y: Sequence[int]) -> None:
        X_list = [list(map(float, row)) for row in X]
        y_list = [int(label) for label in y]

        X_scaled = self.scaler.fit_transform(X_list)

        normal_rows = [row for row, label in zip(X_scaled, y_list) if label == 0]
        if not normal_rows:
            normal_rows = X_scaled
        self.isolation_forest.fit(normal_rows)

        self.xgb_model = xgb.XGBClassifier(n_estimators=100, max_depth=5, learning_rate=0.1)
        self.xgb_model.fit(X_scaled, y_list)

        if shap is not None:  # pragma: no cover - real SHAP only
            try:
                self.explainer = shap.TreeExplainer(self.xgb_model)
            except Exception:  # pragma: no cover - SHAP may fail with stub
                self.explainer = None

        self._persist_models()

    # ------------------------------------------------------------------
    def predict_with_explanation(self, features: Dict[str, float]) -> Dict[str, object]:
        if self.xgb_model is None:
            raise RuntimeError("Model not loaded. Call load_models() first.")

        feature_names = list(features.keys())
        feature_vector = [float(features[name]) for name in feature_names]
        X_scaled = self.scaler.transform([feature_vector])

        iso_score = float(self.isolation_forest.decision_function(X_scaled)[0])
        xgb_prob = float(self.xgb_model.predict_proba(X_scaled)[0][1])
        fraud_score = 0.3 * (-iso_score) + 0.7 * xgb_prob

        explanation = self._build_explanation(feature_names, feature_vector)

        return {
            "is_fraud": bool(fraud_score > 0.5),
            "fraud_score": fraud_score,
            "isolation_forest_score": iso_score,
            "xgb_probability": xgb_prob,
            "explanation": explanation,
        }

    # ------------------------------------------------------------------
    def _build_explanation(self, feature_names: Iterable[str], feature_values: Sequence[float]) -> Dict[str, object]:
        if shap is not None and self.explainer is not None:  # pragma: no cover
            raw_values = self.explainer.shap_values([feature_values])
            if isinstance(raw_values, list):
                shap_values = raw_values[-1][0]
            else:
                shap_values = raw_values[0]
            pairs = list(zip(feature_names, shap_values))
        else:
            importances = getattr(self.xgb_model, "feature_importances_", []) if self.xgb_model else []
            pairs = list(zip(feature_names, importances))

        pairs_sorted = sorted(pairs, key=lambda item: abs(item[1]), reverse=True)[:5]
        feature_map = dict(zip(feature_names, feature_values))
        return {
            "top_factors": [
                {"feature": name, "impact": float(value)}
                for name, value in pairs_sorted
            ],
            "reason": self._human_reason(pairs_sorted, feature_map),
        }

    @staticmethod
    def _human_reason(importance: Iterable[Tuple[str, float]], feature_map: Dict[str, float]) -> str:
        reasons: List[str] = []
        for feature, _ in list(importance)[:3]:
            if feature == "rapid_succession" and feature_map.get(feature):
                reasons.append("Multiple rapid transactions")
            elif feature == "amount_deviation" and feature_map.get(feature, 0) > 3:
                reasons.append("Amount deviates from baseline")
            elif feature == "is_foreign" and feature_map.get(feature):
                reasons.append("Foreign location")
            elif feature == "new_device" and feature_map.get(feature):
                reasons.append("New device fingerprint")
        return " | ".join(reasons) if reasons else "Anomalous feature pattern"

    # ------------------------------------------------------------------
    def _persist_models(self) -> None:
        self.artifacts.ensure()
        with open(self.artifacts.scaler_path, "wb") as fh:
            pickle.dump(self.scaler, fh)
        with open(self.artifacts.isolation_forest_path, "wb") as fh:
            pickle.dump(self.isolation_forest, fh)
        if self.xgb_model is not None:
            self.xgb_model.save_model(self.artifacts.xgb_path)
        if self.explainer is not None and shap is not None:  # pragma: no cover
            explainer_path = self.artifacts.directory / "shap_explainer.pkl"
            with open(explainer_path, "wb") as fh:
                pickle.dump(self.explainer, fh)

    def load_models(self) -> None:
        with open(self.artifacts.scaler_path, "rb") as fh:
            self.scaler = pickle.load(fh)
        with open(self.artifacts.isolation_forest_path, "rb") as fh:
            self.isolation_forest = pickle.load(fh)
        self.xgb_model = xgb.XGBClassifier()
        self.xgb_model.load_model(self.artifacts.xgb_path)
        explainer_path = self.artifacts.directory / "shap_explainer.pkl"
        if shap is not None and explainer_path.exists():  # pragma: no cover
            with open(explainer_path, "rb") as fh:
                self.explainer = pickle.load(fh)

    # ------------------------------------------------------------------
    def export_metadata(self, path: Path) -> None:
        payload = {
            "artifacts": {
                "scaler": str(self.artifacts.scaler_path),
                "isolation_forest": str(self.artifacts.isolation_forest_path),
                "xgb": str(self.artifacts.xgb_path),
            }
        }
        path.write_text(json.dumps(payload, indent=2))


__all__ = ["FraudDetectionModel", "ModelArtifacts"]
