#!/bin/bash
set -e

echo "Starting Ollama..."
ollama serve &

echo "Waiting for Ollama to be ready..."
until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
    sleep 2
done
echo "Ollama is ready."

echo "Pulling qwen2.5:1.5b model (this may take a few minutes on first boot)..."
ollama pull qwen2.5:1.5b
echo "Model ready."

echo "Starting FastAPI..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8001}"
