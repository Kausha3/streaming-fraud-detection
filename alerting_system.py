#!/usr/bin/env python3
"""
Real-time Fraud Alerting System
Monitors transactions and sends alerts through various channels
"""

import asyncio
import json
import smtplib
import aiohttp
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from collections import defaultdict
import os


@dataclass
class Alert:
    """Fraud alert data structure"""
    alert_id: str
    transaction_id: str
    user_id: str
    fraud_score: float
    amount: float
    merchant: str
    timestamp: datetime
    severity: str  # low, medium, high, critical
    alert_type: str  # single_transaction, pattern, velocity, amount_spike
    details: Dict


class AlertRule:
    """Base class for alert rules"""

    def should_alert(self, transaction: Dict, history: List[Dict]) -> Optional[Alert]:
        raise NotImplementedError


class HighRiskTransactionRule(AlertRule):
    """Alert on individual high-risk transactions"""

    def should_alert(self, transaction: Dict, history: List[Dict]) -> Optional[Alert]:
        if transaction["fraud_score"] > 0.8:
            return Alert(
                alert_id=f"alert_{transaction['transaction_id']}",
                transaction_id=transaction["transaction_id"],
                user_id=transaction["user_id"],
                fraud_score=transaction["fraud_score"],
                amount=transaction["amount"],
                merchant=transaction["merchant"],
                timestamp=datetime.utcnow(),
                severity="critical" if transaction["fraud_score"] > 0.9 else "high",
                alert_type="single_transaction",
                details={
                    "reason": "High fraud score detected",
                    "threshold_exceeded": 0.8
                }
            )
        return None


class VelocityRule(AlertRule):
    """Alert on rapid transaction velocity"""

    def should_alert(self, transaction: Dict, history: List[Dict]) -> Optional[Alert]:
        # Check transactions in last 5 minutes
        cutoff_time = datetime.utcnow() - timedelta(minutes=5)
        recent_txns = [
            h for h in history
            if datetime.fromisoformat(h["timestamp"].rstrip("Z")) > cutoff_time
        ]

        if len(recent_txns) > 5:  # More than 5 transactions in 5 minutes
            return Alert(
                alert_id=f"velocity_{transaction['user_id']}_{int(datetime.utcnow().timestamp())}",
                transaction_id=transaction["transaction_id"],
                user_id=transaction["user_id"],
                fraud_score=transaction["fraud_score"],
                amount=transaction["amount"],
                merchant=transaction["merchant"],
                timestamp=datetime.utcnow(),
                severity="high",
                alert_type="velocity",
                details={
                    "reason": "Unusual transaction velocity detected",
                    "transaction_count": len(recent_txns),
                    "time_window": "5 minutes"
                }
            )
        return None


class AmountSpikeRule(AlertRule):
    """Alert on unusual amount patterns"""

    def should_alert(self, transaction: Dict, history: List[Dict]) -> Optional[Alert]:
        if not history:
            return None

        # Calculate average transaction amount
        avg_amount = sum(h["amount"] for h in history) / len(history)

        # Alert if current amount is 5x the average
        if transaction["amount"] > avg_amount * 5:
            return Alert(
                alert_id=f"spike_{transaction['transaction_id']}",
                transaction_id=transaction["transaction_id"],
                user_id=transaction["user_id"],
                fraud_score=transaction["fraud_score"],
                amount=transaction["amount"],
                merchant=transaction["merchant"],
                timestamp=datetime.utcnow(),
                severity="medium",
                alert_type="amount_spike",
                details={
                    "reason": "Transaction amount significantly exceeds user average",
                    "average_amount": round(avg_amount, 2),
                    "spike_ratio": round(transaction["amount"] / avg_amount, 2)
                }
            )
        return None


class GeographicAnomalyRule(AlertRule):
    """Alert on impossible travel patterns"""

    def should_alert(self, transaction: Dict, history: List[Dict]) -> Optional[Alert]:
        if not history:
            return None

        # Check last transaction location
        last_txn = history[-1]
        last_location = last_txn.get("location", "")
        current_location = transaction.get("location", "")

        # Simple check: different countries within 1 hour
        if last_location and current_location:
            last_country = last_location.split(",")[-1].strip()
            current_country = current_location.split(",")[-1].strip()

            time_diff = (
                datetime.fromisoformat(transaction["timestamp"].rstrip("Z")) -
                datetime.fromisoformat(last_txn["timestamp"].rstrip("Z"))
            ).total_seconds() / 3600  # hours

            if last_country != current_country and time_diff < 1:
                return Alert(
                    alert_id=f"geo_{transaction['transaction_id']}",
                    transaction_id=transaction["transaction_id"],
                    user_id=transaction["user_id"],
                    fraud_score=transaction["fraud_score"],
                    amount=transaction["amount"],
                    merchant=transaction["merchant"],
                    timestamp=datetime.utcnow(),
                    severity="high",
                    alert_type="pattern",
                    details={
                        "reason": "Impossible travel detected",
                        "locations": [last_location, current_location],
                        "time_between": f"{time_diff:.1f} hours"
                    }
                )
        return None


class AlertChannel:
    """Base class for alert channels"""

    async def send_alert(self, alert: Alert):
        raise NotImplementedError


class ConsoleAlertChannel(AlertChannel):
    """Print alerts to console"""

    async def send_alert(self, alert: Alert):
        severity_emoji = {
            "low": "📢",
            "medium": "⚠️",
            "high": "🚨",
            "critical": "🔴"
        }

        print(f"\n{severity_emoji[alert.severity]} FRAUD ALERT - {alert.severity.upper()}")
        print(f"Transaction ID: {alert.transaction_id}")
        print(f"User ID: {alert.user_id}")
        print(f"Amount: ${alert.amount:.2f}")
        print(f"Merchant: {alert.merchant}")
        print(f"Fraud Score: {alert.fraud_score:.2%}")
        print(f"Reason: {alert.details['reason']}")
        print("-" * 50)


class WebhookAlertChannel(AlertChannel):
    """Send alerts via webhook"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send_alert(self, alert: Alert):
        payload = {
            "alert_id": alert.alert_id,
            "transaction_id": alert.transaction_id,
            "user_id": alert.user_id,
            "fraud_score": alert.fraud_score,
            "amount": alert.amount,
            "severity": alert.severity,
            "timestamp": alert.timestamp.isoformat(),
            "details": alert.details
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as response:
                    if response.status != 200:
                        print(f"Webhook failed: {response.status}")
        except Exception as e:
            print(f"Webhook error: {e}")


class EmailAlertChannel(AlertChannel):
    """Send alerts via email"""

    def __init__(self, smtp_host: str, smtp_port: int, from_email: str, to_emails: List[str], password: str = ""):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.from_email = from_email
        self.to_emails = to_emails
        self.password = password

    async def send_alert(self, alert: Alert):
        subject = f"[{alert.severity.upper()}] Fraud Alert - Transaction {alert.transaction_id}"

        body = f"""
        FRAUD ALERT DETECTED

        Severity: {alert.severity.upper()}
        Transaction ID: {alert.transaction_id}
        User ID: {alert.user_id}
        Amount: ${alert.amount:.2f}
        Merchant: {alert.merchant}
        Fraud Score: {alert.fraud_score:.2%}

        Alert Details:
        {json.dumps(alert.details, indent=2)}

        Timestamp: {alert.timestamp}

        Please review this transaction immediately.
        """

        try:
            msg = MIMEMultipart()
            msg["From"] = self.from_email
            msg["To"] = ", ".join(self.to_emails)
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))

            # For demo purposes, just print
            print(f"📧 Email Alert: {subject}")
        except Exception as e:
            print(f"Email error: {e}")


class SlackAlertChannel(AlertChannel):
    """Send alerts to Slack"""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    async def send_alert(self, alert: Alert):
        severity_colors = {
            "low": "#36a64f",
            "medium": "#ff9900",
            "high": "#ff0000",
            "critical": "#800080"
        }

        payload = {
            "attachments": [{
                "color": severity_colors[alert.severity],
                "title": f"Fraud Alert - {alert.severity.upper()}",
                "fields": [
                    {"title": "Transaction ID", "value": alert.transaction_id, "short": True},
                    {"title": "User ID", "value": alert.user_id, "short": True},
                    {"title": "Amount", "value": f"${alert.amount:.2f}", "short": True},
                    {"title": "Fraud Score", "value": f"{alert.fraud_score:.2%}", "short": True},
                    {"title": "Merchant", "value": alert.merchant, "short": False},
                    {"title": "Reason", "value": alert.details["reason"], "short": False}
                ],
                "footer": "Fraud Detection System",
                "ts": int(alert.timestamp.timestamp())
            }]
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload) as response:
                    if response.status != 200:
                        print(f"Slack webhook failed: {response.status}")
        except Exception as e:
            print(f"Slack error: {e}")


class FraudAlertingSystem:
    """Main alerting system that coordinates rules and channels"""

    def __init__(self):
        self.rules: List[AlertRule] = []
        self.channels: List[AlertChannel] = []
        self.transaction_history = defaultdict(list)
        self.alert_history: List[Alert] = []
        self.suppression_window = 300  # 5 minutes in seconds

    def add_rule(self, rule: AlertRule):
        """Add an alert rule"""
        self.rules.append(rule)

    def add_channel(self, channel: AlertChannel):
        """Add an alert channel"""
        self.channels.append(channel)

    async def process_transaction(self, transaction: Dict):
        """Process a transaction through all rules"""
        user_id = transaction["user_id"]
        user_history = self.transaction_history[user_id]

        # Check all rules
        alerts = []
        for rule in self.rules:
            alert = rule.should_alert(transaction, user_history)
            if alert and not self._is_duplicate_alert(alert):
                alerts.append(alert)
                self.alert_history.append(alert)

        # Send alerts through all channels
        for alert in alerts:
            for channel in self.channels:
                await channel.send_alert(alert)

        # Update history
        self.transaction_history[user_id].append(transaction)

        # Keep only last 100 transactions per user
        if len(self.transaction_history[user_id]) > 100:
            self.transaction_history[user_id] = self.transaction_history[user_id][-100:]

        return alerts

    def _is_duplicate_alert(self, alert: Alert) -> bool:
        """Check if this alert was recently sent"""
        cutoff_time = datetime.utcnow() - timedelta(seconds=self.suppression_window)

        for historical_alert in self.alert_history:
            if (historical_alert.user_id == alert.user_id and
                historical_alert.alert_type == alert.alert_type and
                historical_alert.timestamp > cutoff_time):
                return True
        return False

    def get_alert_statistics(self) -> Dict:
        """Get alerting statistics"""
        now = datetime.utcnow()
        last_hour = now - timedelta(hours=1)
        last_day = now - timedelta(days=1)

        stats = {
            "total_alerts": len(self.alert_history),
            "alerts_last_hour": sum(1 for a in self.alert_history if a.timestamp > last_hour),
            "alerts_last_day": sum(1 for a in self.alert_history if a.timestamp > last_day),
            "alerts_by_severity": defaultdict(int),
            "alerts_by_type": defaultdict(int)
        }

        for alert in self.alert_history:
            stats["alerts_by_severity"][alert.severity] += 1
            stats["alerts_by_type"][alert.alert_type] += 1

        return dict(stats)


async def monitor_live_stream():
    """Monitor live WebSocket stream for fraud alerts"""

    # Initialize alerting system
    alerting_system = FraudAlertingSystem()

    # Add rules
    alerting_system.add_rule(HighRiskTransactionRule())
    alerting_system.add_rule(VelocityRule())
    alerting_system.add_rule(AmountSpikeRule())
    alerting_system.add_rule(GeographicAnomalyRule())

    # Add channels
    alerting_system.add_channel(ConsoleAlertChannel())

    # Add webhook if configured
    webhook_url = os.getenv("ALERT_WEBHOOK_URL")
    if webhook_url:
        alerting_system.add_channel(WebhookAlertChannel(webhook_url))

    # Add Slack if configured
    slack_webhook = os.getenv("SLACK_WEBHOOK_URL")
    if slack_webhook:
        alerting_system.add_channel(SlackAlertChannel(slack_webhook))

    print("🚨 Real-Time Fraud Alerting System Started")
    print("Monitoring for suspicious patterns...\n")

    # Connect to WebSocket
    try:
        import websockets

        uri = "ws://localhost:8000/ws/live"
        async with websockets.connect(uri) as websocket:
            async for message in websocket:
                try:
                    transaction = json.loads(message)

                    # Process through alerting system
                    alerts = await alerting_system.process_transaction(transaction)

                    # Print statistics periodically
                    if len(alerting_system.alert_history) % 10 == 0:
                        stats = alerting_system.get_alert_statistics()
                        print(f"\n📊 Alert Statistics: {stats}\n")

                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    print(f"Error processing transaction: {e}")

    except Exception as e:
        print(f"WebSocket connection error: {e}")
        print("Make sure the fraud detection API is running")


async def demo_alerting():
    """Demo the alerting system with test data"""

    alerting_system = FraudAlertingSystem()

    # Add all rules
    alerting_system.add_rule(HighRiskTransactionRule())
    alerting_system.add_rule(VelocityRule())
    alerting_system.add_rule(AmountSpikeRule())
    alerting_system.add_rule(GeographicAnomalyRule())

    # Add console channel for demo
    alerting_system.add_channel(ConsoleAlertChannel())

    print("🎮 Running Alerting System Demo\n")

    # Simulate transactions
    test_transactions = [
        # Normal transaction
        {
            "transaction_id": "tx_001",
            "user_id": "user_demo",
            "amount": 50.00,
            "merchant": "Coffee Shop",
            "location": "New York, US",
            "fraud_score": 0.1,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        },
        # High risk transaction
        {
            "transaction_id": "tx_002",
            "user_id": "user_demo",
            "amount": 5000.00,
            "merchant": "Online Casino",
            "location": "Moscow, Russia",
            "fraud_score": 0.95,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        },
        # Rapid transactions (velocity)
        *[{
            "transaction_id": f"tx_00{i}",
            "user_id": "user_velocity",
            "amount": 100.00,
            "merchant": "Various Stores",
            "location": "Los Angeles, US",
            "fraud_score": 0.4,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        } for i in range(3, 10)],
        # Amount spike
        {
            "transaction_id": "tx_010",
            "user_id": "user_spike",
            "amount": 10000.00,
            "merchant": "Luxury Store",
            "location": "Paris, France",
            "fraud_score": 0.6,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
    ]

    # Process transactions
    for txn in test_transactions:
        await alerting_system.process_transaction(txn)
        await asyncio.sleep(0.5)  # Small delay for readability

    # Print final statistics
    print("\n" + "=" * 50)
    print("📊 FINAL ALERT STATISTICS")
    stats = alerting_system.get_alert_statistics()
    for key, value in stats.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    import sys

    print("🚨 FRAUD DETECTION ALERTING SYSTEM\n")
    print("Usage:")
    print("  python alerting_system.py demo    - Run demo with test data")
    print("  python alerting_system.py monitor - Monitor live transactions\n")

    if len(sys.argv) > 1 and sys.argv[1] == "demo":
        asyncio.run(demo_alerting())
    else:
        try:
            asyncio.run(monitor_live_stream())
        except KeyboardInterrupt:
            print("\n\nAlerting system stopped")