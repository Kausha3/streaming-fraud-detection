.PHONY: infra down logs generator perf frontend api stream

infra:
	@docker compose up -d zookeeper kafka redis postgres

stream:
	@docker compose up --build stream-processor

api:
	@docker compose up --build api

frontend:
	@docker compose up --build frontend

logs:
	@docker compose logs -f

generator:
	@python3 src/generator/transaction_generator.py --broker localhost:9092 --topic transactions --tps 100

perf:
	@python3 performance_test.py --requests 10000 --concurrency 200 --base-url http://localhost:8000

down:
	@docker compose down
