"""FastAPI backend powering transaction checks and analytics."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from functools import lru_cache
from typing import Any, Dict, Optional

import asyncpg
from aiokafka import AIOKafkaProducer
from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import redis.asyncio as aioredis

# Allow access to shared src modules when mounted into the container
import sys
from pathlib import Path

APP_ROOT = Path(os.getenv("APP_ROOT", ".")).resolve()
SRC_PATH = APP_ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.append(str(SRC_PATH))

from feature_store.feature_engineering import FeatureEngine  # type: ignore  # noqa: E402
from models.fraud_model import FraudDetectionModel  # type: ignore  # noqa: E402

logger = logging.getLogger(__name__)


class TransactionRequest(BaseModel):
    user_id: str
    amount: float
    merchant: str
    location: str
    device_id: str
    transaction_type: str


class FraudResponse(BaseModel):
    transaction_id: str
    is_fraud: bool
    fraud_score: float
    explanation: Dict[str, Any]
    processing_time_ms: float


class AppState:
    """Container for shared resources."""

    def __init__(self) -> None:
        self.kafka_producer: Optional[AIOKafkaProducer] = None
        self.redis: Optional[aioredis.Redis] = None
        self.pg_pool: Optional[asyncpg.pool.Pool] = None
        self.feature_engine = FeatureEngine()
        self.model = FraudDetectionModel()

    async def init(self) -> None:
        await self._init_kafka()
        await self._init_redis()
        await self._init_postgres()
        try:
            self.model.load_models()
        except Exception as exc:  # pragma: no cover - guard during early setup
            logger.warning("Could not load model artifacts: %s", exc)

    async def shutdown(self) -> None:
        if self.kafka_producer is not None:
            await self.kafka_producer.stop()
        if self.redis is not None:
            await self.redis.close()
        if self.pg_pool is not None:
            await self.pg_pool.close()

    async def _init_kafka(self) -> None:
        broker = os.getenv("KAFKA_BROKER", "kafka:9092")
        max_retries = 10
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                producer = AIOKafkaProducer(bootstrap_servers=broker)
                await producer.start()
                self.kafka_producer = producer
                logger.info("Kafka producer connected to %s", broker)
                return
            except Exception as exc:
                logger.warning("Kafka connection attempt %d/%d failed: %s", attempt + 1, max_retries, exc)
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, 10)  # Exponential backoff with cap
                else:
                    logger.error("Failed to connect to Kafka after %d attempts", max_retries)
                    raise

    async def _init_redis(self) -> None:
        host = os.getenv("REDIS_HOST", "redis")
        port = int(os.getenv("REDIS_PORT", "6379"))
        redis_client = aioredis.Redis(host=host, port=port, decode_responses=True)
        self.redis = redis_client
        logger.info("Redis client initialised %s:%s", host, port)

    async def _init_postgres(self) -> None:
        dsn = os.getenv("DATABASE_URL", "postgresql://postgres:password@postgres/fraud_detection")
        try:
            self.pg_pool = await asyncpg.create_pool(dsn)
            logger.info("Postgres pool created")
        except Exception as exc:  # pragma: no cover
            logger.warning("Postgres connection skipped: %s", exc)


@lru_cache(maxsize=1)
def get_state() -> AppState:
    return AppState()


app = FastAPI(title="Fraud Detection API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    state = get_state()
    await state.init()


@app.on_event("shutdown")
async def on_shutdown() -> None:
    state = get_state()
    await state.shutdown()


@app.post("/api/v1/transaction/check", response_model=FraudResponse)
async def check_transaction(request: TransactionRequest, state: AppState = Depends(get_state)) -> FraudResponse:
    if state.kafka_producer is None:
        raise HTTPException(status_code=500, detail="Kafka producer unavailable")

    tx_id = str(uuid.uuid4())
    payload = request.model_dump()
    payload["transaction_id"] = tx_id
    payload["timestamp"] = _timestamp_iso()

    loop = asyncio.get_running_loop()
    start = loop.time()

    # Publish to Kafka
    message_bytes = json.dumps(payload, default=str).encode("utf-8")
    await state.kafka_producer.send_and_wait(os.getenv("KAFKA_TOPIC", "transactions"), message_bytes)

    result = await wait_for_result(tx_id, state.redis)
    if result is None:
        logger.debug("Result not ready in time; running sync fallback")
        result = await process_sync(payload, state)

    processing_time_ms = (loop.time() - start) * 1000

    # Update processing_time_ms in result
    result["processing_time_ms"] = processing_time_ms

    # Save to database
    if state.pg_pool is not None:
        try:
            async with state.pg_pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO transactions (transaction_id, user_id, amount, merchant, location, device_id, transaction_type, is_fraud, fraud_score)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """,
                    tx_id,
                    payload["user_id"],
                    float(payload["amount"]),
                    payload.get("merchant", "Unknown"),
                    payload.get("location", "Unknown"),
                    payload.get("device_id", "Unknown"),
                    payload.get("transaction_type", "Unknown"),
                    result["is_fraud"],
                    result["fraud_score"],
                )
        except Exception as e:
            logger.warning(f"Failed to save transaction to database: {e}")

    # Send to WebSocket clients via Redis
    if state.redis is not None:
        try:
            ws_message = json.dumps({
                "transaction_id": tx_id,
                "user_id": payload["user_id"],
                "amount": payload["amount"],
                "merchant": payload.get("merchant", "Unknown"),
                "is_fraud": result["is_fraud"],
                "fraud_score": result["fraud_score"],
                "timestamp": _timestamp_iso(),
            })
            await state.redis.publish("live_transactions", ws_message)
        except Exception as e:
            logger.warning(f"Failed to publish to Redis: {e}")

    return FraudResponse(
        transaction_id=tx_id,
        **result,
    )


async def wait_for_result(transaction_id: str, redis_client: Optional[aioredis.Redis], timeout: float = 0.1) -> Optional[Dict[str, Any]]:
    if redis_client is None:
        return None

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    key = f"result:{transaction_id}"
    while loop.time() < deadline:
        data = await redis_client.get(key)
        if data:
            await redis_client.delete(key)
            return json.loads(data)
        await asyncio.sleep(0.01)
    return None


async def process_sync(transaction: Dict[str, Any], state: AppState) -> Dict[str, Any]:
    loop = asyncio.get_running_loop()

    def _compute() -> Dict[str, Any]:
        features = state.feature_engine.extract_features({**transaction, "timestamp": _timestamp_iso()})
        prediction = state.model.predict_with_explanation(features)
        return {
            "is_fraud": prediction["is_fraud"],
            "fraud_score": prediction["fraud_score"],
            "explanation": prediction["explanation"],
            "processing_time_ms": 0.0,
        }

    return await loop.run_in_executor(None, _compute)


def _timestamp_iso() -> str:
    from datetime import datetime

    return datetime.utcnow().isoformat()


@app.get("/api/v1/stats/overview")
async def get_overview_stats(state: AppState = Depends(get_state)) -> Dict[str, Any]:
    if state.redis is None:
        raise HTTPException(status_code=500, detail="Redis unavailable")

    cache_key = "stats:overview"
    cached = await state.redis.get(cache_key)
    if cached:
        return json.loads(cached)

    if state.pg_pool is None:
        raise HTTPException(status_code=500, detail="Database unavailable")

    async with state.pg_pool.acquire() as conn:
        total_transactions = await conn.fetchval("SELECT COUNT(*) FROM transactions")
        fraud_detected = await conn.fetchval("SELECT COUNT(*) FROM transactions WHERE is_fraud = true")
        fraud_amount = await conn.fetchval("SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE is_fraud = true")
        avg_latency = await conn.fetchval(
            "SELECT AVG(fraud_score) FROM transactions WHERE created_at > NOW() - INTERVAL '1 hour'"
        )

    # Calculate transactions per second from last minute
    async with state.pg_pool.acquire() as conn:
        recent_count = await conn.fetchval(
            "SELECT COUNT(*) FROM transactions WHERE created_at > NOW() - INTERVAL '1 minute'"
        )

    tps = (recent_count or 0) / 60.0 if recent_count else 0.0

    stats = {
        "total_transactions": total_transactions or 0,
        "fraud_detected": fraud_detected or 0,
        "fraud_prevented_amount": float(fraud_amount or 0),
        "detection_accuracy": 0.95 if total_transactions > 10 else 0.0,  # Mock accuracy for demo
        "avg_processing_time_ms": float(avg_latency or 0) * 1000 if avg_latency else 0.0,
        "transactions_per_second": round(tps, 2),
    }

    await state.redis.setex(cache_key, 10, json.dumps(stats))
    return stats


@app.get("/api/v1/transactions/{transaction_id}")
async def get_transaction_details(transaction_id: str, state: AppState = Depends(get_state)) -> Dict[str, Any]:
    if state.redis is not None:
        cached = await state.redis.get(f"tx:{transaction_id}")
        if cached:
            return json.loads(cached)

    if state.pg_pool is None:
        raise HTTPException(status_code=500, detail="Database unavailable")

    async with state.pg_pool.acquire() as conn:
        record = await conn.fetchrow(
            "SELECT * FROM transactions WHERE transaction_id = $1",
            transaction_id,
        )
    if record is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return dict(record)


@app.get("/api/v1/users/{user_id}/risk-profile")
async def get_user_risk_profile(user_id: str, state: AppState = Depends(get_state)) -> Dict[str, Any]:
    if state.pg_pool is None:
        raise HTTPException(status_code=500, detail="Database unavailable")

    async with state.pg_pool.acquire() as conn:
        total_transactions = await conn.fetchval(
            "SELECT COUNT(*) FROM transactions WHERE user_id = $1",
            user_id,
        )
        fraud_attempts = await conn.fetchval(
            "SELECT COUNT(*) FROM transactions WHERE user_id = $1 AND is_fraud = true",
            user_id,
        )
        risk_score = await conn.fetchval("SELECT AVG(fraud_score) FROM transactions WHERE user_id = $1", user_id)
    return {
        "user_id": user_id,
        "total_transactions": total_transactions or 0,
        "fraud_attempts": fraud_attempts or 0,
        "risk_score": float(risk_score or 0),
        "unusual_patterns": [],  # Placeholder; will integrate with analytics phase
        "device_fingerprints": [],
    }


@app.websocket("/ws/live")
async def websocket_endpoint(websocket: WebSocket, state: AppState = Depends(get_state)) -> None:
    if state.redis is None:
        await websocket.close(code=1011)
        return

    await websocket.accept()
    pubsub = state.redis.pubsub()
    await pubsub.subscribe("live_transactions")

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message.get("type") == "message":
                await websocket.send_text(message["data"])  # data already json string
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    finally:
        await pubsub.unsubscribe("live_transactions")
        await pubsub.close()
        await websocket.close()
