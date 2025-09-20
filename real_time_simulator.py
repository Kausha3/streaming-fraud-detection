#!/usr/bin/env python3
"""
Real-time Transaction Simulator
Simulates realistic e-commerce/payment transactions for fraud detection
"""
import asyncio
import random
import json
import time
from datetime import datetime
import aiohttp
from typing import Dict, List

# Configuration
API_URL = "http://localhost:8000/api/v1/transaction/check"
TRANSACTIONS_PER_SECOND = 2  # Adjust for load testing

# Realistic data pools
MERCHANTS = {
    "Amazon": {"category": "online", "risk": 0.1},
    "Walmart": {"category": "retail", "risk": 0.1},
    "Gas Station #423": {"category": "gas", "risk": 0.3},
    "Online Casino XYZ": {"category": "gambling", "risk": 0.8},
    "Crypto Exchange": {"category": "crypto", "risk": 0.7},
    "Apple Store": {"category": "electronics", "risk": 0.1},
    "Unknown Merchant 999": {"category": "unknown", "risk": 0.9},
    "ATM Withdrawal": {"category": "cash", "risk": 0.4},
    "Wire Transfer Intl": {"category": "transfer", "risk": 0.6},
}

LOCATIONS = [
    "New York, NY", "Los Angeles, CA", "Chicago, IL",
    "Houston, TX", "Phoenix, AZ", "Philadelphia, PA",
    "Lagos, Nigeria", "Moscow, Russia", "Unknown Location"
]

# User profiles for realistic patterns
USER_PROFILES = {
    "normal_user": {
        "transaction_amounts": (10, 500),
        "merchants": ["Amazon", "Walmart", "Apple Store", "Gas Station #423"],
        "locations": ["New York, NY", "Los Angeles, CA"],
        "fraud_probability": 0.02
    },
    "high_risk_user": {
        "transaction_amounts": (100, 5000),
        "merchants": ["Online Casino XYZ", "Crypto Exchange", "Wire Transfer Intl"],
        "locations": ["Unknown Location", "Lagos, Nigeria", "Moscow, Russia"],
        "fraud_probability": 0.3
    },
    "business_user": {
        "transaction_amounts": (500, 10000),
        "merchants": ["Amazon", "Apple Store", "Wire Transfer Intl"],
        "locations": ["New York, NY", "Chicago, IL"],
        "fraud_probability": 0.05
    }
}

class TransactionSimulator:
    def __init__(self):
        self.total_sent = 0
        self.fraudulent_count = 0
        self.start_time = time.time()
        self.user_devices = {}  # Track devices per user

    def generate_transaction(self) -> Dict:
        """Generate a realistic transaction"""
        # Select user type
        user_type = random.choices(
            ["normal_user", "high_risk_user", "business_user"],
            weights=[70, 20, 10]
        )[0]

        profile = USER_PROFILES[user_type]
        user_id = f"{user_type}_{random.randint(1, 100)}"

        # Get or create device for user
        if user_id not in self.user_devices:
            self.user_devices[user_id] = f"device_{random.randint(1000, 9999)}"

        # Sometimes use a new device (suspicious)
        if random.random() < 0.1:
            device_id = f"new_device_{random.randint(10000, 99999)}"
        else:
            device_id = self.user_devices[user_id]

        # Select merchant
        if random.random() < profile["fraud_probability"]:
            # Fraudulent transaction patterns
            merchant_name = random.choice(["Unknown Merchant 999", "Online Casino XYZ", "Crypto Exchange"])
            amount = random.uniform(1000, 10000)
            location = random.choice(["Unknown Location", "Lagos, Nigeria", "Moscow, Russia"])
            transaction_type = "CARD_NOT_PRESENT"
            self.fraudulent_count += 1
        else:
            # Normal transaction
            merchant_name = random.choice(profile["merchants"])
            amount = random.uniform(*profile["transaction_amounts"])
            location = random.choice(profile["locations"])
            transaction_type = random.choice(["purchase", "online", "CARD_NOT_PRESENT"])

        merchant_info = MERCHANTS.get(merchant_name, {"category": "unknown", "risk": 0.5})

        return {
            "user_id": user_id,
            "amount": round(amount, 2),
            "merchant": merchant_name,
            "category": merchant_info["category"],
            "location": location,
            "device_id": device_id,
            "transaction_type": transaction_type,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

    async def send_transaction(self, session: aiohttp.ClientSession, transaction: Dict):
        """Send transaction to API"""
        try:
            async with session.post(API_URL, json=transaction) as response:
                if response.status == 200:
                    result = await response.json()
                    self.total_sent += 1

                    # Print results
                    fraud_status = "🚨 FRAUD" if result["is_fraud"] else "✅ LEGIT"
                    score = result["fraud_score"]
                    print(f"{fraud_status} | Score: {score:.2%} | "
                          f"${transaction['amount']:.2f} at {transaction['merchant'][:20]} | "
                          f"User: {transaction['user_id'][:15]}")

                    # Alert on high fraud scores
                    if score > 0.7:
                        print(f"⚠️  HIGH RISK ALERT: Transaction {result['transaction_id']}")

                    return result
                else:
                    print(f"Error: {response.status}")
        except Exception as e:
            print(f"Failed to send transaction: {e}")

    async def run_simulation(self, duration_seconds: int = 60):
        """Run the simulation for specified duration"""
        print("🚀 Starting Real-Time Transaction Simulator")
        print(f"Duration: {duration_seconds} seconds")
        print(f"Rate: {TRANSACTIONS_PER_SECOND} transactions/second")
        print("-" * 60)

        async with aiohttp.ClientSession() as session:
            tasks = []
            end_time = time.time() + duration_seconds

            while time.time() < end_time:
                # Generate and send transaction
                transaction = self.generate_transaction()
                task = asyncio.create_task(self.send_transaction(session, transaction))
                tasks.append(task)

                # Control rate
                await asyncio.sleep(1.0 / TRANSACTIONS_PER_SECOND)

                # Clean up completed tasks
                if len(tasks) > 100:
                    done, tasks = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                    tasks = list(tasks)

            # Wait for remaining tasks
            if tasks:
                await asyncio.gather(*tasks)

        # Print summary
        elapsed = time.time() - self.start_time
        print("\n" + "=" * 60)
        print("📊 SIMULATION SUMMARY")
        print(f"Total Transactions: {self.total_sent}")
        print(f"Fraudulent Patterns: {self.fraudulent_count}")
        print(f"Average TPS: {self.total_sent/elapsed:.2f}")
        print(f"Detection Rate: {(self.fraudulent_count/self.total_sent*100):.1f}%")

async def main():
    simulator = TransactionSimulator()
    await simulator.run_simulation(duration_seconds=30)  # Run for 30 seconds

if __name__ == "__main__":
    print("\n🏦 REAL-TIME FRAUD DETECTION SIMULATOR")
    print("This simulates a payment gateway sending transactions for fraud checks")
    print("\nPress Ctrl+C to stop\n")

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nSimulation stopped by user")