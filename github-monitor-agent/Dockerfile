FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data
ENV DB_PATH=/data/agent_memory.db

CMD ["python", "scheduler.py"]
