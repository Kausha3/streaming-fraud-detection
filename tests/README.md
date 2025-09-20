# Test Strategy Roadmap

This directory will house unit, integration, and stream regression tests once data persistence is fully wired up.

- **Unit**: `pytest` suites for feature extraction utilities and model wrappers (mock Redis, load synthetic features).
- **Integration**: spin up docker-compose stack in CI, seed sample transactions, assert API endpoints & WebSocket flow using `httpx`/`pytest-asyncio`.
- **Performance/Soak**: integrate `performance_test.py` into a CI job with configurable load to track latency/throughput regressions over time.

Add new test modules alongside the relevant components as subsequent phases come online.
