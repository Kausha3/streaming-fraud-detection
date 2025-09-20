"""Async load generator targeting the FastAPI transaction endpoint."""
from __future__ import annotations

import argparse
import asyncio
import random
import statistics
import time
from dataclasses import dataclass
from typing import List

import aiohttp


@dataclass
class TestConfig:
    base_url: str
    total_requests: int
    concurrency: int


class PerformanceTest:
    def __init__(self, config: TestConfig) -> None:
        self.config = config
        self.latencies: List[float] = []
        self.errors: List[str] = []

    async def _send_transaction(self, session: aiohttp.ClientSession) -> None:
        payload = {
            "user_id": f"user_{random.randint(1, 1000)}",
            "amount": round(random.uniform(10, 5000), 2),
            "merchant": random.choice(["Amazon", "Walmart", "Target", "Starbucks"]),
            "location": random.choice(["USA", "Canada", "Mexico", "UK"]),
            "device_id": f"device_{random.randint(1, 100)}",
            "transaction_type": random.choice(["CARD_PRESENT", "CARD_NOT_PRESENT"]),
        }

        start = time.perf_counter()
        try:
            async with session.post(f"{self.config.base_url}/api/v1/transaction/check", json=payload, timeout=2) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    self.errors.append(f"HTTP {resp.status}: {body}")
                    return
                await resp.json()
        except Exception as exc:  # noqa: BLE001 - capturing for reporting
            self.errors.append(str(exc))
            return
        finally:
            latency_ms = (time.perf_counter() - start) * 1000
            self.latencies.append(latency_ms)

    async def run(self) -> None:
        connector = aiohttp.TCPConnector(limit=self.config.concurrency)
        async with aiohttp.ClientSession(connector=connector) as session:
            semaphore = asyncio.Semaphore(self.config.concurrency)

            async def runner(_: int) -> None:
                async with semaphore:
                    await self._send_transaction(session)

            await asyncio.gather(*(runner(i) for i in range(self.config.total_requests)))

    def report(self) -> str:
        if not self.latencies:
            return "No results collected"

        stats_lines = [
            "=== Performance Test Results ===",
            f"Total Requests: {self.config.total_requests}",
            f"Successful: {self.config.total_requests - len(self.errors)}",
            f"Failed: {len(self.errors)}",
            "",
            "Latency Statistics (ms):",
            f"  Min: {min(self.latencies):.2f}",
            f"  Max: {max(self.latencies):.2f}",
            f"  Mean: {statistics.mean(self.latencies):.2f}",
            f"  Median: {statistics.median(self.latencies):.2f}",
            f"  P95: {self._percentile(95):.2f}",
            f"  P99: {self._percentile(99):.2f}",
        ]

        total_time = sum(self.latencies) / 1000
        throughput = (self.config.total_requests - len(self.errors)) / (total_time / self.config.concurrency)
        stats_lines.append("")
        stats_lines.append(f"Throughput: {throughput:.2f} TPS")

        if self.errors:
            stats_lines.append("")
            stats_lines.append("Sample Errors:")
            stats_lines.extend(f"  - {err}" for err in self.errors[:5])

        return "\n".join(stats_lines)

    def _percentile(self, percentile: float) -> float:
        if not self.latencies:
            return 0.0
        ordered = sorted(self.latencies)
        if len(ordered) == 1:
            return ordered[0]
        rank = (percentile / 100) * (len(ordered) - 1)
        lower = int(rank)
        upper = min(lower + 1, len(ordered) - 1)
        fraction = rank - lower
        return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


async def main_async(config: TestConfig) -> None:
    tester = PerformanceTest(config)
    await tester.run()
    print(tester.report())


def parse_args() -> TestConfig:
    parser = argparse.ArgumentParser(description="Load test the transaction check endpoint")
    parser.add_argument("--base-url", default="http://localhost:8000", help="Base URL for the API")
    parser.add_argument("--requests", type=int, default=1000, help="Number of requests to send")
    parser.add_argument("--concurrency", type=int, default=100, help="Concurrent requests")
    args = parser.parse_args()
    return TestConfig(base_url=args.base_url, total_requests=args.requests, concurrency=args.concurrency)


def main() -> None:
    config = parse_args()
    asyncio.run(main_async(config))


if __name__ == "__main__":
    main()
