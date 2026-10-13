FROM python:3.11-slim

RUN useradd -m -u 1000 user
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libopus0 \
    libopus-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R user:user /app
USER user

EXPOSE 8000
ENV PORT=8000
CMD ["python", "-u", "xiaozhi_private_server.py"]
