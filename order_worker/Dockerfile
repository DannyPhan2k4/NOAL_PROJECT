FROM python:3.9-slim

WORKDIR /app

# Cài đặt thư viện hệ thống cần thiết cho psycopg2 (PostgreSQL driver)
RUN apt-get update && apt-get install -y libpq-dev gcc

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY worker.py .

CMD ["python", "-u", "worker.py"]