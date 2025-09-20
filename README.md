# Real-Time Fraud Detection Engine

This repository tracks the build-out of the "Streaming Fraud Detection Engine" portfolio project. Phase 1 delivers the core streaming infrastructure and synthetic data generator that will fuel downstream machine learning and analytics components.

## Architecture

## Runbook

- `make infra` – start Kafka/Zookeeper, Redis, Postgres
- `make stream` / `make api` / `make frontend` – build + run specific services
- `make generator` – launch the synthetic transaction publisher (press Ctrl+C to stop)
- `make perf` – execute the async load test at 10k requests / 200 concurrent
- `./scripts/bootstrap_demo.sh` – full end-to-end demo setup (brings up stack then launches generator)

```
[Transaction Stream] → [Kafka] → [Spark Streaming] → [ML Ensemble]
                              ↓                   ↓
                        [Redis Cache]        [PostgreSQL]
                              ↓                   ↓
                       [FastAPI Backend] ↔ [React Dashboard]
                              ↓
                       [Alert Service]* → Slack/Email
```

*Alert service placeholder to be implemented once persistence hooks are complete.

## Phase 1 — Core Infrastructure

### Prerequisites
- Docker & Docker Compose
- Python 3.10+

### Services
`docker-compose.yml` starts the foundational services required for local development:
- Kafka + Zookeeper for streaming ingestion
- Redis for low-latency feature caching (placeholder for future phases)
- PostgreSQL initialised with a `transactions` table skeleton

```bash
# From the repository root
docker-compose up -d
```

### Synthetic Transaction Generator
The generator in `src/generator/transaction_generator.py` produces a mix of normal and fraudulent transactions and publishes them to the `transactions` Kafka topic.

```bash
# Optional: create a virtual environment
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python src/generator/transaction_generator.py --broker localhost:9092 --topic transactions --tps 100
```

Flags allow you to tweak the fraud rate, throughput and Kafka bootstrap server.

## Next Steps
Upcoming phases will layer feature engineering, ML models, stream processing (Spark/Flink), a FastAPI backend, and a React dashboard on top of this foundation.

## Phase 2 — Feature Engineering & Models

### Feature Store Utilities
`src/feature_store/feature_engineering.py` houses the Redis-backed feature engine that extracts velocity, device, and behavioural signals per transaction. It keeps a rolling user history to mirror the streaming pipeline.

### Model Ensemble
`src/models/fraud_model.py` wraps an Isolation Forest + XGBoost ensemble (with pure-Python fallbacks) and persists artefacts for downstream consumers. Generate demo artefacts with:

```bash
python scripts/train_dummy_model.py
```

## Phase 3 — Stream Processing Engine

### Spark Structured Streaming Job
The Spark driver lives in `stream-processor/app/stream_processor.py`. It consumes the Kafka topic, derives features via the shared `FeatureEngine`, executes ensemble inference with `FraudDetectionModel`, writes enriched transactions into PostgreSQL, and fans out real-time alerts/results over Redis for the API and dashboard.

### Running the Processor
1. Train or copy model artefacts into `./artifacts` so the container can load them.
2. Launch infrastructure and the processor: `docker-compose up --build stream-processor`.
3. Make sure `./src` is mounted read-only into the container (handled by the compose file) so feature/model modules stay in sync.

Checkpoint data lands in `/tmp/spark-checkpoints` inside the container. Adjust `KAFKA_BROKER`, `KAFKA_TOPIC`, or `CHECKPOINT_DIR` via environment variables if needed.

## Phase 4 — FastAPI Backend

The backend lives in `backend/app/main.py` and exposes transaction scoring, stats, detail lookup, user risk profile, and WebSocket feeds. It reuses the shared feature engine + model artefacts and publishes to Kafka while polling Redis/Postgres for results, falling back to synchronous scoring if the stream lag exceeds the 100ms budget.

### Run Locally
```bash
# Build and start the API alongside dependencies
docker-compose up --build api
```
Expose port `8000` for REST + WebSockets. Environment variables (Kafka broker, Redis host, database URL) can be tweaked in `docker-compose.yml`.

## Phase 5 — React Dashboard

The frontend lives in `frontend/` and ships a Vite + Tailwind React dashboard with live WebSocket feeds and Chart.js visualisations. It proxies API/WebSocket calls back to the FastAPI service when running locally.

### Run Locally
```bash
# Build and serve the compiled dashboard via Docker
docker-compose up --build frontend
```
Once up, open http://localhost:3000 to view live metrics, transaction feed, and fraud alerts.

## Phase 6 — Testing & Benchmarking

`performance_test.py` drives the FastAPI scoring endpoint with configurable volume/concurrency to validate the 100K TPS goal. Example:

```bash
python performance_test.py --requests 10000 --concurrency 200 --base-url http://localhost:8000
```

Extend this phase with pytest/httpx suites and stream integration tests once the persistence hooks are implemented.

## Performance Targets

- Throughput: 100,000 TPS (via synthetic generator + load test)
- Latency: p50 25ms, p95 75ms, p99 95ms (target values; validate with `performance_test.py`)
- Accuracy: 96.5% detection rate, 2.1% false positive rate (requires model training data)
- Fraud Prevented: $2M in simulated scenarios

## Demo Checklist

1. Run `./scripts/bootstrap_demo.sh` to start the stack and generator.
2. Confirm FastAPI health at http://localhost:8000/docs.
3. Open the dashboard at http://localhost:3000 and watch live transactions populate.
4. Execute `make perf` (optional) to collect current latency/throughput metrics.
