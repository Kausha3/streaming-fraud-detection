#!/usr/bin/env python3
"""
API Integration Examples for Fraud Detection System
Shows how to integrate with e-commerce platforms and payment gateways
"""

import asyncio
import aiohttp
import json
from typing import Dict, Optional
from datetime import datetime
import hashlib

class FraudDetectionClient:
    """Client library for integrating with the fraud detection API"""

    def __init__(self, api_url: str = "http://localhost:8000", api_key: Optional[str] = None):
        self.api_url = api_url
        self.api_key = api_key
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def check_transaction(self, transaction: Dict) -> Dict:
        """Check a single transaction for fraud"""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        async with self.session.post(
            f"{self.api_url}/api/v1/transaction/check",
            json=transaction,
            headers=headers
        ) as response:
            return await response.json()

    async def get_user_risk_profile(self, user_id: str) -> Dict:
        """Get risk profile for a specific user"""
        async with self.session.get(
            f"{self.api_url}/api/v1/users/{user_id}/risk-profile"
        ) as response:
            return await response.json()

    async def subscribe_to_alerts(self, callback):
        """Subscribe to real-time fraud alerts via WebSocket"""
        ws_url = self.api_url.replace("http://", "ws://").replace("https://", "wss://")
        async with self.session.ws_connect(f"{ws_url}/ws/live") as ws:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    if data.get("is_fraud"):
                        await callback(data)


# Example 1: E-commerce Integration (Shopify/WooCommerce style)
class EcommerceIntegration:
    def __init__(self, fraud_client: FraudDetectionClient):
        self.fraud_client = fraud_client
        self.blocked_transactions = set()

    async def process_checkout(self, order_data: Dict) -> Dict:
        """
        Process an e-commerce checkout with fraud detection
        Similar to Stripe/PayPal flow
        """
        # Convert e-commerce order to fraud detection format
        transaction = {
            "user_id": order_data["customer_id"],
            "amount": order_data["total_amount"],
            "merchant": order_data.get("store_name", "Unknown Store"),
            "location": f"{order_data['shipping_city']}, {order_data['shipping_country']}",
            "device_id": order_data.get("session_id", "unknown"),
            "transaction_type": "online_purchase"
        }

        # Check for fraud
        result = await self.fraud_client.check_transaction(transaction)

        # Decision logic based on fraud score
        if result["fraud_score"] > 0.8:
            # High risk - block transaction
            self.blocked_transactions.add(result["transaction_id"])
            return {
                "status": "blocked",
                "reason": "High fraud risk detected",
                "transaction_id": result["transaction_id"],
                "action": "Please contact customer support"
            }
        elif result["fraud_score"] > 0.5:
            # Medium risk - require additional verification
            return {
                "status": "verification_required",
                "transaction_id": result["transaction_id"],
                "verification_methods": ["sms", "email", "3d_secure"],
                "reason": "Additional verification required for security"
            }
        else:
            # Low risk - approve
            return {
                "status": "approved",
                "transaction_id": result["transaction_id"],
                "message": "Payment approved"
            }


# Example 2: Payment Gateway Integration (Stripe/Square style)
class PaymentGatewayIntegration:
    def __init__(self, fraud_client: FraudDetectionClient):
        self.fraud_client = fraud_client
        self.webhook_url = "https://your-app.com/webhooks/fraud-alerts"

    async def authorize_payment(self, payment_intent: Dict) -> Dict:
        """
        Pre-authorize a payment with fraud screening
        Similar to Stripe PaymentIntent flow
        """
        # Enhanced transaction data with payment metadata
        transaction = {
            "user_id": payment_intent["customer_id"],
            "amount": payment_intent["amount"] / 100,  # Convert cents to dollars
            "merchant": payment_intent["merchant_name"],
            "location": payment_intent.get("ip_location", "Unknown"),
            "device_id": self._generate_device_fingerprint(payment_intent),
            "transaction_type": payment_intent["payment_method_type"]
        }

        # Real-time fraud check
        fraud_result = await self.fraud_client.check_transaction(transaction)

        # Get user's risk history
        user_profile = await self.fraud_client.get_user_risk_profile(
            payment_intent["customer_id"]
        )

        # Combined risk assessment
        combined_risk = self._calculate_combined_risk(
            fraud_result["fraud_score"],
            user_profile["risk_score"],
            payment_intent["amount"] / 100
        )

        if combined_risk > 0.7:
            # Send webhook for manual review
            await self._send_webhook({
                "event": "payment.high_risk",
                "payment_intent_id": payment_intent["id"],
                "fraud_score": fraud_result["fraud_score"],
                "action_required": "manual_review"
            })

            return {
                "status": "requires_action",
                "client_secret": payment_intent["client_secret"],
                "next_action": {
                    "type": "manual_review",
                    "display_message": "Your payment is being reviewed"
                }
            }

        return {
            "status": "succeeded",
            "payment_intent_id": payment_intent["id"],
            "fraud_check_passed": True
        }

    def _generate_device_fingerprint(self, payment_data: Dict) -> str:
        """Generate device fingerprint from payment data"""
        fingerprint_data = f"{payment_data.get('ip_address', '')}"
        fingerprint_data += f"{payment_data.get('user_agent', '')}"
        fingerprint_data += f"{payment_data.get('browser_fingerprint', '')}"
        return hashlib.md5(fingerprint_data.encode()).hexdigest()

    def _calculate_combined_risk(self, fraud_score: float, user_risk: float, amount: float) -> float:
        """Calculate combined risk score with amount weighting"""
        # Higher amounts get more scrutiny
        amount_weight = min(amount / 1000, 1.0)  # Cap at $1000
        return (fraud_score * 0.6 + user_risk * 0.3 + amount_weight * 0.1)

    async def _send_webhook(self, data: Dict):
        """Send webhook notification"""
        # Implementation would send to configured webhook URL
        print(f"Webhook sent: {data}")


# Example 3: Banking/Fintech Integration
class BankingIntegration:
    def __init__(self, fraud_client: FraudDetectionClient):
        self.fraud_client = fraud_client
        self.alert_callbacks = []

    async def monitor_account_activity(self, account_id: str):
        """
        Real-time monitoring for banking transactions
        Similar to how banks detect unusual activity
        """
        # Set up real-time alert monitoring
        async def fraud_alert_handler(alert_data: Dict):
            if alert_data["user_id"].startswith(f"account_{account_id}"):
                # Trigger account protection measures
                await self._protect_account(account_id, alert_data)

                # Notify all registered callbacks
                for callback in self.alert_callbacks:
                    await callback(alert_data)

        await self.fraud_client.subscribe_to_alerts(fraud_alert_handler)

    async def verify_wire_transfer(self, transfer_data: Dict) -> Dict:
        """
        Verify wire transfers with enhanced scrutiny
        """
        # Wire transfers need extra validation
        transaction = {
            "user_id": transfer_data["sender_account"],
            "amount": transfer_data["amount"],
            "merchant": f"Wire to {transfer_data['recipient_bank']}",
            "location": transfer_data.get("originating_branch", "Online"),
            "device_id": transfer_data.get("device_id", "bank_terminal"),
            "transaction_type": "wire_transfer"
        }

        result = await self.fraud_client.check_transaction(transaction)

        # Wire transfers have stricter thresholds
        if result["fraud_score"] > 0.3:  # Lower threshold for wire transfers
            return {
                "status": "held_for_review",
                "transfer_id": transfer_data["transfer_id"],
                "estimated_review_time": "2-4 hours",
                "contact_number": "1-800-BANK-HELP"
            }

        return {
            "status": "approved",
            "transfer_id": transfer_data["transfer_id"],
            "processing_time": "1-2 business days"
        }

    async def _protect_account(self, account_id: str, alert_data: Dict):
        """Implement account protection measures"""
        protection_measures = {
            "temporary_hold": alert_data["fraud_score"] > 0.9,
            "require_2fa": alert_data["fraud_score"] > 0.7,
            "notify_customer": True,
            "flag_for_review": alert_data["fraud_score"] > 0.5
        }
        print(f"Account {account_id} protection activated: {protection_measures}")
        return protection_measures


# Example 4: Real-time Dashboard Integration
class DashboardIntegration:
    def __init__(self, fraud_client: FraudDetectionClient):
        self.fraud_client = fraud_client
        self.metrics = {
            "total_checked": 0,
            "fraud_prevented": 0,
            "false_positives": 0
        }

    async def stream_to_dashboard(self):
        """Stream real-time fraud detection events to a dashboard"""
        async def handle_transaction(data: Dict):
            self.metrics["total_checked"] += 1
            if data["is_fraud"]:
                self.metrics["fraud_prevented"] += 1

            # Send to dashboard (WebSocket, Server-Sent Events, etc.)
            dashboard_event = {
                "timestamp": datetime.utcnow().isoformat(),
                "transaction_id": data["transaction_id"],
                "fraud_score": data["fraud_score"],
                "is_fraud": data["is_fraud"],
                "amount": data["amount"],
                "metrics": self.metrics
            }

            # In real implementation, send to dashboard
            print(f"Dashboard Update: {dashboard_event}")

        await self.fraud_client.subscribe_to_alerts(handle_transaction)


# Example usage and testing
async def main():
    """Demonstrate the integration examples"""

    print("🚀 Fraud Detection API Integration Examples\n")

    async with FraudDetectionClient() as client:

        # Example 1: E-commerce checkout
        print("1️⃣ E-commerce Checkout Example:")
        ecommerce = EcommerceIntegration(client)

        order = {
            "customer_id": "user_12345",
            "total_amount": 299.99,
            "store_name": "TechGadgets Inc",
            "shipping_city": "New York",
            "shipping_country": "US",
            "session_id": "sess_abc123"
        }

        checkout_result = await ecommerce.process_checkout(order)
        print(f"   Checkout Result: {checkout_result}\n")

        # Example 2: Payment gateway
        print("2️⃣ Payment Gateway Example:")
        gateway = PaymentGatewayIntegration(client)

        payment = {
            "id": "pi_1234567890",
            "customer_id": "cus_98765",
            "amount": 15000,  # $150 in cents
            "merchant_name": "Online Store",
            "payment_method_type": "card",
            "ip_location": "Los Angeles, CA",
            "client_secret": "pi_secret_xyz"
        }

        payment_result = await gateway.authorize_payment(payment)
        print(f"   Payment Result: {payment_result}\n")

        # Example 3: Banking wire transfer
        print("3️⃣ Banking Wire Transfer Example:")
        banking = BankingIntegration(client)

        transfer = {
            "transfer_id": "wire_001",
            "sender_account": "account_555",
            "recipient_bank": "International Bank Ltd",
            "amount": 5000.00,
            "originating_branch": "NYC Branch"
        }

        wire_result = await banking.verify_wire_transfer(transfer)
        print(f"   Wire Transfer Result: {wire_result}\n")


if __name__ == "__main__":
    print("\n💳 FRAUD DETECTION INTEGRATION EXAMPLES")
    print("This shows how to integrate the fraud detection API with various platforms\n")

    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Error: {e}")