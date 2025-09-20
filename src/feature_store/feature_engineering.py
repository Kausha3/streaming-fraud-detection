"""Feature engineering helpers for streaming fraud detection."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd
import redis


@dataclass
class RedisConfig:
    host: str = "redis"  # Changed from localhost to redis container name
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    history_length: int = 100


class FeatureEngine:
    """Derives real-time features from a transaction stream."""

    def __init__(self, redis_config: Optional[RedisConfig] = None) -> None:
        self.redis_config = redis_config or RedisConfig()
        self.redis_client = redis.Redis(
            host=self.redis_config.host,
            port=self.redis_config.port,
            db=self.redis_config.db,
            password=self.redis_config.password,
            decode_responses=True,
        )
        self.feature_window_seconds = 300  # five minute lookback

    # -- public API -----------------------------------------------------
    def extract_features(self, transaction: Dict) -> Dict:
        """Build a flat feature dictionary for downstream models."""
        user_id = transaction["user_id"]
        user_history = self._get_user_history(user_id)

        features = {
            # transaction metadata
            "amount": float(transaction["amount"]),
            "hour_of_day": self._parse_timestamp(transaction["timestamp"]).hour,
            "day_of_week": self._parse_timestamp(transaction["timestamp"]).weekday(),
            "is_weekend": int(self._parse_timestamp(transaction["timestamp"]).weekday() >= 5),
            # velocity features
            "tx_count_1min": self._count_recent_transactions(user_history, 60),
            "tx_count_5min": self._count_recent_transactions(user_history, 300),
            "amount_sum_1min": self._sum_recent_amounts(user_history, 60),
            "amount_sum_5min": self._sum_recent_amounts(user_history, 300),
            # location/device intelligence
            "location_change": int(self._detect_location_change(transaction, user_history)),
            "is_foreign": int(transaction.get("location") not in {"USA", "Canada"}),
            "new_device": int(self._is_new_device(transaction, user_history)),
            "device_count": self._count_unique_devices(user_history),
            # behavioural baselines
            "amount_deviation": self._calculate_amount_deviation(transaction, user_history),
            "merchant_frequency": self._merchant_frequency(transaction, user_history),
            # rule hints
            "card_not_present": int(transaction.get("transaction_type") == "CARD_NOT_PRESENT"),
            "rapid_succession": int(self._detect_rapid_succession(user_history)),
            "duplicate_amount": int(self._detect_duplicate_amount(transaction, user_history)),
        }

        # Update rolling history after computing features to avoid contamination
        self._append_to_history(user_id, transaction)
        return features

    def _get_user_history(self, user_id: str) -> List[Dict]:
        history = self.redis_client.lrange(self._history_key(user_id), 0, self.redis_config.history_length - 1)
        return [json.loads(item) for item in history]

    # -- individual feature helpers ------------------------------------
    @staticmethod
    def _parse_timestamp(timestamp: str) -> datetime:
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc)

    def _count_recent_transactions(self, history: Sequence[Dict], seconds: int) -> int:
        cutoff = datetime.utcnow().replace(tzinfo=timezone.utc)
        return sum(
            1 for tx in history if (cutoff - self._parse_timestamp(tx["timestamp"]).astimezone(timezone.utc)).total_seconds() <= seconds
        )

    def _sum_recent_amounts(self, history: Sequence[Dict], seconds: int) -> float:
        cutoff = datetime.utcnow().replace(tzinfo=timezone.utc)
        return float(
            sum(
                float(tx["amount"])
                for tx in history
                if (cutoff - self._parse_timestamp(tx["timestamp"]).astimezone(timezone.utc)).total_seconds() <= seconds
            )
        )

    def _detect_location_change(self, transaction: Dict, history: Sequence[Dict]) -> bool:
        if not history:
            return False
        last_location = history[0].get("location")
        return bool(last_location and last_location != transaction.get("location"))

    def _is_new_device(self, transaction: Dict, history: Sequence[Dict]) -> bool:
        device_id = transaction.get("device_id")
        return device_id not in {tx.get("device_id") for tx in history}

    def _count_unique_devices(self, history: Sequence[Dict]) -> int:
        return len({tx.get("device_id") for tx in history if tx.get("device_id")})

    def _calculate_amount_deviation(self, transaction: Dict, history: Sequence[Dict]) -> float:
        if not history:
            return 0.0
        amounts = np.array([float(tx["amount"]) for tx in history[:20]])
        if amounts.size <= 1:
            return 0.0
        mean = np.mean(amounts)
        std = np.std(amounts)
        if std == 0:
            return 0.0
        return abs(float(transaction["amount"]) - mean) / std

    def _merchant_frequency(self, transaction: Dict, history: Sequence[Dict]) -> float:
        merchant = transaction.get("merchant")
        if not history or not merchant:
            return 0.0
        occurrences = sum(1 for tx in history if tx.get("merchant") == merchant)
        return occurrences / len(history)

    def _detect_rapid_succession(self, history: Sequence[Dict]) -> bool:
        if len(history) < 4:
            return False
        timestamps = [self._parse_timestamp(tx["timestamp"]).astimezone(timezone.utc) for tx in history[:5]]
        timestamps.sort()
        return (timestamps[-1] - timestamps[0]).total_seconds() <= 60

    def _detect_duplicate_amount(self, transaction: Dict, history: Sequence[Dict]) -> bool:
        amount = round(float(transaction["amount"]), 2)
        return any(round(float(tx["amount"]), 2) == amount for tx in history[:10])

    # -- persistence helpers -------------------------------------------
    def _append_to_history(self, user_id: str, transaction: Dict) -> None:
        key = self._history_key(user_id)
        self.redis_client.lpush(key, json.dumps(transaction))
        self.redis_client.ltrim(key, 0, self.redis_config.history_length - 1)

    def _history_key(self, user_id: str) -> str:
        return f"user_history:{user_id}"


__all__ = ["FeatureEngine", "RedisConfig"]
