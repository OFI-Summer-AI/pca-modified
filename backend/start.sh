#!/bin/bash
set -e

# Start Ollama in background
echo "Starting Ollama..."
ollama serve &

# Pull model in background — don't block FastAPI startup
(
    echo "Waiting for Ollama to be ready..."
    until curl -s http://localhost:11434/api/tags > /dev/null 2>&1; do
        sleep 2
    done
    echo "Pulling qwen2.5:1.5b..."
    ollama pull qwen2.5:1.5b
    echo "Model ready."
) &

# Start FastAPI immediately so Railway health check passes
echo "Starting FastAPI..."
exec uvicorn main:app --host 0.0.0.0 --port "${PORT:-8001}"
