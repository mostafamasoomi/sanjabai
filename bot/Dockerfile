FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py .
CMD ["python", "bot.py"]
HEALTHCHECK --interval=60s --timeout=5s --start-period=15s --retries=3 \
  CMD ["python", "-c", "import os,signal; os.kill(1,0)"]
