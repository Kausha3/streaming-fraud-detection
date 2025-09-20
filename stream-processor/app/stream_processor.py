"""Spark Structured Streaming job for fraud detection."""
from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from typing import Dict

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.functions import col, from_json
from pyspark.sql.types import (DoubleType, StringType, StructField,
                               StructType)

import psycopg
import redis

# Allow imports from the monorepo src directory when mounted
ROOT_DIR = os.getenv("APP_ROOT", "/app")
SRC_PATH = os.path.join(ROOT_DIR, "src")
if SRC_PATH not in sys.path:
    sys.path.append(SRC_PATH)

from feature_store.feature_engineering import FeatureEngine, RedisConfig  # type: ignore  # noqa: E402
from models.fraud_model import FraudDetectionModel  # type: ignore  # noqa: E402

logger = logging.getLogger(__name__)


@dataclass
class ProcessorConfig:
    kafka_broker: str = os.getenv("KAFKA_BROKER", "kafka:9092")
    kafka_topic: str = os.getenv("KAFKA_TOPIC", "transactions")
    checkpoint_dir: str = os.getenv("CHECKPOINT_DIR", "/tmp/spark-checkpoints")
    database_url: str = os.getenv("DATABASE_URL", "postgresql://postgres:password@postgres/fraud_detection")
    redis_host: str = os.getenv("REDIS_HOST", "redis")
    redis_port: int = int(os.getenv("REDIS_PORT", "6379"))
    redis_alert_channel: str = os.getenv("REDIS_ALERT_CHANNEL", "fraud_alerts")
    redis_cache_ttl: int = int(os.getenv("REDIS_CACHE_TTL", "300"))
    redis_result_ttl: int = int(os.getenv("REDIS_RESULT_TTL", "30"))


class StreamProcessor:
    """Coordinates Kafka ingestion, feature extraction, and model inference."""

    def __init__(self, config: ProcessorConfig | None = None) -> None:
        self.config = config or ProcessorConfig()
        self.spark = self._create_spark_session()
        self.feature_engine = FeatureEngine(
            RedisConfig(host=self.config.redis_host, port=self.config.redis_port)
        )
        self.model = FraudDetectionModel()
        self.redis_client = self._init_redis()
        self.pg_conn = self._init_postgres()

        try:
            self.model.load_models()
        except Exception as exc:  # pragma: no cover - runtime guard
            logger.warning("Could not load model artifacts: %s", exc)

    def _create_spark_session(self) -> SparkSession:
        return (
            SparkSession.builder.appName("FraudDetection")
            .config("spark.sql.shuffle.partitions", "4")
            .config("spark.streaming.kafka.maxRatePerPartition", "1000")
            .getOrCreate()
        )

    def _init_redis(self) -> redis.Redis | None:
        try:
            client = redis.Redis(
                host=self.config.redis_host,
                port=self.config.redis_port,
                decode_responses=True,
            )
            client.ping()
            logger.info("Connected to Redis at %s:%s", self.config.redis_host, self.config.redis_port)
            return client
        except Exception as exc:  # pragma: no cover - runtime guard
            logger.warning("Redis unavailable: %s", exc)
            return None

    def _init_postgres(self) -> psycopg.Connection | None:
        try:
            conn = psycopg.connect(self.config.database_url, autocommit=True)
            logger.info("Connected to Postgres: %s", self.config.database_url)
            return conn
        except Exception as exc:  # pragma: no cover - runtime guard
            logger.warning("Postgres unavailable: %s", exc)
            return None

    def start(self) -> None:
        logger.info(
            "Starting stream processor for topic=%s broker=%s",
            self.config.kafka_topic,
            self.config.kafka_broker,
        )

        raw_stream = (
            self.spark.readStream.format("kafka")
            .option("kafka.bootstrap.servers", self.config.kafka_broker)
            .option("subscribe", self.config.kafka_topic)
            .option("startingOffsets", "latest")
            .load()
        )
        parsed_stream = self._parse_transactions(raw_stream)

        query = (
            parsed_stream.writeStream.foreachBatch(self._process_batch)
            .option("checkpointLocation", self.config.checkpoint_dir)
            .outputMode("update")
            .start()
        )

        query.awaitTermination()

    def _parse_transactions(self, stream_df: DataFrame) -> DataFrame:
        schema = StructType([
            StructField("transaction_id", StringType()),
            StructField("user_id", StringType()),
            StructField("amount", DoubleType()),
            StructField("merchant", StringType()),
            StructField("location", StringType()),
            StructField("timestamp", StringType()),
            StructField("device_id", StringType()),
            StructField("transaction_type", StringType()),
        ])
        return (
            stream_df.select(from_json(col("value").cast("string"), schema).alias("data"))
            .select("data.*")
            .dropna(subset=["transaction_id", "user_id", "amount"])
        )

    def _process_batch(self, batch_df: DataFrame, batch_id: int) -> None:
        logger.info("Processing batch_id=%s with %s records", batch_id, batch_df.count())
        rows = batch_df.collect()
        for row in rows:
            transaction = row.asDict(recursive=True)
            self._handle_transaction(transaction)

    def _handle_transaction(self, transaction: Dict) -> None:
        logger.debug("Handling transaction %s", transaction.get("transaction_id"))
        features = self.feature_engine.extract_features(transaction)

        try:
            prediction = self.model.predict_with_explanation(features)
        except Exception as exc:
            logger.exception("Model inference failed: %s", exc)
            return

        enriched = {**transaction, "fraud_detection": prediction}
        self._persist_result(enriched)
        if prediction.get("is_fraud"):
            self._emit_alert(enriched)

    def _persist_result(self, enriched: Dict) -> None:
        prediction = enriched.get("fraud_detection", {})
        tx_id = enriched.get("transaction_id")

        if self.pg_conn is not None and tx_id is not None:
            try:
                with self.pg_conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO transactions (
                            transaction_id, user_id, amount, merchant, location,
                            device_id, transaction_type, is_fraud, fraud_score, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (transaction_id) DO UPDATE SET
                            user_id = EXCLUDED.user_id,
                            amount = EXCLUDED.amount,
                            merchant = EXCLUDED.merchant,
                            location = EXCLUDED.location,
                            device_id = EXCLUDED.device_id,
                            transaction_type = EXCLUDED.transaction_type,
                            is_fraud = EXCLUDED.is_fraud,
                            fraud_score = EXCLUDED.fraud_score
                        """,
                        (
                            tx_id,
                            enriched.get("user_id"),
                            float(enriched.get("amount", 0.0)),
                            enriched.get("merchant"),
                            enriched.get("location"),
                            enriched.get("device_id"),
                            enriched.get("transaction_type"),
                            bool(prediction.get("is_fraud", False)),
                            float(prediction.get("fraud_score", 0.0)),
                            self._coerce_timestamp(enriched.get("timestamp")),
                        ),
                    )
            except Exception as exc:  # pragma: no cover - runtime guard
                logger.exception("Failed to persist transaction %s: %s", tx_id, exc)

        if self.redis_client is not None and tx_id is not None:
            try:
                cache_payload = json.dumps(enriched, default=str)
                self.redis_client.setex(
                    f"tx:{tx_id}",
                    self.config.redis_cache_ttl,
                    cache_payload,
                )
                result_payload = json.dumps(
                    {
                        "transaction_id": tx_id,
                        "is_fraud": bool(prediction.get("is_fraud", False)),
                        "fraud_score": float(prediction.get("fraud_score", 0.0)),
                        "explanation": prediction.get("explanation", {}),
                    },
                    default=str,
                )
                self.redis_client.setex(
                    f"result:{tx_id}",
                    self.config.redis_result_ttl,
                    result_payload,
                )
            except Exception as exc:  # pragma: no cover - runtime guard
                logger.warning("Failed to cache transaction %s: %s", tx_id, exc)

    def _emit_alert(self, enriched: Dict) -> None:
        logger.info(
            "Fraud detected transaction_id=%s user_id=%s score=%.2f",
            enriched.get("transaction_id"),
            enriched.get("user_id"),
            enriched["fraud_detection"]["fraud_score"],
        )
        if self.redis_client is None:
            return
        try:
            self.redis_client.publish(
                self.config.redis_alert_channel,
                json.dumps(enriched, default=str),
            )
        except Exception as exc:  # pragma: no cover - runtime guard
            logger.warning("Failed to publish alert for %s: %s", enriched.get("transaction_id"), exc)

    def _coerce_timestamp(self, value):
        from datetime import datetime

        if value is None:
            return datetime.utcnow()
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return datetime.utcnow()


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    processor = StreamProcessor()
    processor.start()


if __name__ == "__main__":
    main()
