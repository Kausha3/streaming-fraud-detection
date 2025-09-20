# Real-Time Fraud Detection System - Usage Guide

## 🚀 Quick Start

### 1. Start the System
```bash
docker-compose up -d
```

### 2. Run the Real-Time Simulator
```bash
python3 real_time_simulator.py
```

### 3. View Dashboard
Open http://localhost:3000 in your browser to see live fraud detection metrics

## 📊 Real-Time Features

### Live Transaction Stream
- **WebSocket Connection**: Real-time updates at `ws://localhost:8000/ws/live`
- **Transaction Rate**: 2 TPS (configurable in simulator)
- **Fraud Patterns**: Automatically generates suspicious patterns

### Dashboard Metrics
- **Transactions/Second**: Real-time throughput
- **Fraud Prevented Amount**: Running total of blocked fraudulent transactions
- **Detection Accuracy**: ML model performance (XGBoost + Isolation Forest ensemble)
- **Average Latency**: Sub-300ms processing time

## 🔧 Integration Methods

### 1. REST API Integration
```python
import aiohttp
import json

async def check_transaction(transaction_data):
    async with aiohttp.ClientSession() as session:
        async with session.post(
            'http://localhost:8000/api/v1/transaction/check',
            json=transaction_data
        ) as response:
            return await response.json()

# Example transaction
transaction = {
    "user_id": "customer_123",
    "amount": 150.00,
    "merchant": "Amazon",
    "location": "New York, NY",
    "device_id": "device_456",
    "transaction_type": "online"
}

result = await check_transaction(transaction)
if result['fraud_score'] > 0.7:
    print("⚠️ High risk transaction detected!")
```

### 2. WebSocket Real-Time Alerts
```python
import websockets
import json

async def monitor_fraud():
    uri = "ws://localhost:8000/ws/live"
    async with websockets.connect(uri) as websocket:
        async for message in websocket:
            data = json.loads(message)
            if data['is_fraud']:
                print(f"🚨 FRAUD ALERT: Transaction {data['transaction_id']}")
                # Trigger your alert system
```

### 3. Batch Processing
```python
# Run the API integration examples
python3 api_integration_examples.py
```

## 💡 Use Cases

### E-commerce Platform
1. Install fraud detection at checkout
2. Block high-risk transactions automatically
3. Require additional verification for medium-risk
4. Approve low-risk instantly

### Payment Gateway
1. Pre-authorize payments with fraud screening
2. Calculate combined risk scores
3. Send webhooks for manual review
4. Implement 3D Secure for suspicious transactions

### Banking/Fintech
1. Monitor account activity in real-time
2. Hold wire transfers for review
3. Implement account protection measures
4. Send instant fraud notifications

## 🎯 Fraud Detection Logic

### Risk Scoring
- **0.0 - 0.3**: Low risk (approve)
- **0.3 - 0.7**: Medium risk (additional verification)
- **0.7 - 1.0**: High risk (block/manual review)

### Feature Analysis
The system analyzes 17 features including:
- Transaction amount patterns
- Merchant risk categories
- Geographic anomalies
- Device fingerprinting
- User behavior patterns
- Time-based patterns

### ML Models
- **XGBoost**: Primary classification model
- **Isolation Forest**: Anomaly detection
- **Ensemble**: Combined scoring for accuracy

## 📈 Performance Tuning

### Increase Transaction Rate
Edit `real_time_simulator.py`:
```python
TRANSACTIONS_PER_SECOND = 10  # Increase from 2
```

### Adjust Fraud Patterns
Modify user profiles in simulator:
```python
USER_PROFILES = {
    "normal_user": {
        "fraud_probability": 0.02  # 2% fraud rate
    },
    "high_risk_user": {
        "fraud_probability": 0.3   # 30% fraud rate
    }
}
```

### Scale Components
```yaml
# docker-compose.yml
services:
  api:
    deploy:
      replicas: 3  # Scale API instances
```

## 🔍 Monitoring

### Check System Health
```bash
# View all container logs
docker-compose logs -f

# Check specific service
docker-compose logs api
docker-compose logs stream-processor

# Monitor Kafka topics
docker exec -it kafka kafka-topics.sh --list --bootstrap-server localhost:9092
```

### Database Queries
```sql
-- Recent fraud attempts
SELECT * FROM transactions
WHERE is_fraud = true
ORDER BY created_at DESC
LIMIT 10;

-- User risk profiles
SELECT user_id, AVG(fraud_score) as avg_risk
FROM transactions
GROUP BY user_id
ORDER BY avg_risk DESC;
```

## 🛠️ Troubleshooting

### Dashboard Shows Zeros
1. Check if simulator is running
2. Verify API is accessible: `curl http://localhost:8000/api/v1/stats/overview`
3. Check browser console for errors

### High Latency
1. Check Redis connection: `docker exec -it redis redis-cli ping`
2. Monitor Kafka lag
3. Scale stream processor if needed

### False Positives
1. Retrain models with more data
2. Adjust fraud score thresholds
3. Add business rules for known patterns

## 🚦 Production Deployment

### Security
- Add API authentication
- Use HTTPS/WSS for connections
- Encrypt sensitive data
- Implement rate limiting

### Scaling
- Use Kubernetes for orchestration
- Implement horizontal pod autoscaling
- Use managed Kafka (Confluent/AWS MSK)
- Consider cloud ML services

### Monitoring
- Add Prometheus metrics
- Use Grafana dashboards
- Implement alerting (PagerDuty/Opsgenie)
- Track business KPIs

## 📚 API Reference

### Check Transaction
```
POST /api/v1/transaction/check
{
  "user_id": "string",
  "amount": 0.0,
  "merchant": "string",
  "location": "string",
  "device_id": "string",
  "transaction_type": "string"
}
```

### Get Stats
```
GET /api/v1/stats/overview
```

### User Risk Profile
```
GET /api/v1/users/{user_id}/risk-profile
```

### WebSocket Stream
```
WS /ws/live
```

## 🎮 Demo Mode

Run the complete demo:
```bash
# Terminal 1: Start system
docker-compose up

# Terminal 2: Run simulator
python3 real_time_simulator.py

# Terminal 3: Test integrations
python3 api_integration_examples.py

# Browser: View dashboard
open http://localhost:3000
```

This creates a fully functional real-time fraud detection environment!