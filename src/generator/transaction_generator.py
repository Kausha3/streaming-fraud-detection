"""Synthetic transaction generator for driving the Kafka fraud detection topic."""
from __future__ import annotations

import argparse
import json
import logging
import random
import signal
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from kafka import KafkaProducer


logger = logging.getLogger(__name__)


@dataclass
class GeneratorConfig:
    """Runtime configuration for the generator."""

    broker: str = "localhost:9092"
    topic: str = "transactions"
    fraud_rate: float = 0.1
    target_tps: int = 100
    flush_interval: int = 100

    @property
    def sleep_interval(self) -> float:
        return 1.0 / self.target_tps if self.target_tps > 0 else 0.0


class TransactionGenerator:
    """Continuously pushes synthetic transactions to Kafka."""

    def __init__(self, config: GeneratorConfig) -> None:
        self.config = config
        self._should_run = True

        self.producer = KafkaProducer(
            bootstrap_servers=[self.config.broker],
            value_serializer=lambda value: json.dumps(value).encode("utf-8"),
            linger_ms=5,
        )

        # Templates for normal vs fraudulent behaviour patterns
        self.normal_merchants = ["Amazon", "Walmart", "Target", "Starbucks"]
        self.normal_amount_range = (10, 500)
        self.normal_device_range = (1, 100)

        self.fraud_amount_range = (5000, 10000)
        self.fraud_locations = ["Nigeria", "Russia", "Romania"]
        self.fraud_device_range = (1, 5)

    def _generate_transaction(self, is_fraud: bool) -> dict:
        now_iso = datetime.utcnow().isoformat()
        base = {
            "transaction_id": str(uuid.uuid4()),
            "user_id": f"user_{random.randint(1, 1000)}",
            "merchant": random.choice(self.normal_merchants),
            "timestamp": now_iso,
        }

        if is_fraud:
            amount = random.uniform(*self.fraud_amount_range)
            device_suffix = random.randint(*self.fraud_device_range)
            location = random.choice(self.fraud_locations)
            transaction_type = "CARD_NOT_PRESENT"
        else:
            amount = random.uniform(*self.normal_amount_range)
            device_suffix = random.randint(*self.normal_device_range)
            location = "USA"
            transaction_type = "CARD_PRESENT"

        return {
            **base,
            "amount": round(amount, 2),
            "location": location,
            "device_id": f"device_{device_suffix}",
            "transaction_type": transaction_type,
            "is_fraud": is_fraud,
        }

    def run(self) -> None:
        sent = 0
        logger.info(
            "Starting generator: broker=%s topic=%s fraud_rate=%.2f target_tps=%d",
            self.config.broker,
            self.config.topic,
            self.config.fraud_rate,
            self.config.target_tps,
        )

        try:
            while self._should_run:
                is_fraud = random.random() < self.config.fraud_rate
                payload = self._generate_transaction(is_fraud)
                self.producer.send(self.config.topic, value=payload)
                sent += 1

                if sent % self.config.flush_interval == 0:
                    self.producer.flush()
                    logger.debug("Flushed %d messages", sent)

                if self.config.sleep_interval:
                    time.sleep(self.config.sleep_interval)
        except KeyboardInterrupt:
            logger.info("Stopping generator (keyboard interrupt)")
        finally:
            self.producer.flush(timeout=5)
            self.producer.close()
            logger.info("Generator shut down cleanly")

    def stop(self) -> None:
        self._should_run = False


def parse_args(argv: Optional[Iterable[str]] = None) -> GeneratorConfig:
    parser = argparse.ArgumentParser(description="Kafka transaction load generator")
    parser.add_argument("--broker", default="localhost:9092", help="Kafka bootstrap server")
    parser.add_argument("--topic", default="transactions", help="Kafka topic to publish to")
    parser.add_argument(
        "--fraud-rate",
        type=float,
        default=0.1,
        help="Fraction of transactions that should be flagged as fraud",
    )
    parser.add_argument(
        "--tps",
        type=int,
        default=100,
        help="Target transactions per second",
    )
    parser.add_argument(
        "--flush-interval",
        type=int,
        default=100,
        help="Number of records to buffer before forcing a flush",
    )

    args = parser.parse_args(argv)

    return GeneratorConfig(
        broker=args.broker,
        topic=args.topic,
        fraud_rate=args.fraud_rate,
        target_tps=args.tps,
        flush_interval=args.flush_interval,
    )


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def main(argv: Optional[Iterable[str]] = None) -> None:
    _configure_logging()
    config = parse_args(argv)
    generator = TransactionGenerator(config)

    def handle_sigterm(signum, frame):  # type: ignore[unused-argument]
        logger.info("Received signal %s; shutting down", signum)
        generator.stop()

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)
    generator.run()


if __name__ == "__main__":
    main(sys.argv[1:])
