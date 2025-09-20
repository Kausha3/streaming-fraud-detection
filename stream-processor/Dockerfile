FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-21-jre-headless wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Download Kafka dependencies for PySpark
ENV SPARK_VERSION=3.5.1
ENV SCALA_VERSION=2.12
RUN mkdir -p /usr/local/lib/python3.10/site-packages/pyspark/jars && \
    wget -q https://repo1.maven.org/maven2/org/apache/spark/spark-sql-kafka-0-10_${SCALA_VERSION}/${SPARK_VERSION}/spark-sql-kafka-0-10_${SCALA_VERSION}-${SPARK_VERSION}.jar \
         -O /usr/local/lib/python3.10/site-packages/pyspark/jars/spark-sql-kafka-0-10_${SCALA_VERSION}-${SPARK_VERSION}.jar && \
    wget -q https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/3.5.1/kafka-clients-3.5.1.jar \
         -O /usr/local/lib/python3.10/site-packages/pyspark/jars/kafka-clients-3.5.1.jar && \
    wget -q https://repo1.maven.org/maven2/org/apache/spark/spark-token-provider-kafka-0-10_${SCALA_VERSION}/${SPARK_VERSION}/spark-token-provider-kafka-0-10_${SCALA_VERSION}-${SPARK_VERSION}.jar \
         -O /usr/local/lib/python3.10/site-packages/pyspark/jars/spark-token-provider-kafka-0-10_${SCALA_VERSION}-${SPARK_VERSION}.jar && \
    wget -q https://repo1.maven.org/maven2/org/apache/commons/commons-pool2/2.12.0/commons-pool2-2.12.0.jar \
         -O /usr/local/lib/python3.10/site-packages/pyspark/jars/commons-pool2-2.12.0.jar

COPY app ./app

CMD ["python", "-m", "app.stream_processor"]
