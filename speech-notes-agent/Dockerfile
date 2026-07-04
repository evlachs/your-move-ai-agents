FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data /app/audio
ENV DB_PATH=/data/agent_memory.db
ENV AUDIO_DIR=/app/audio

CMD ["python", "main.py"]
