#!/bin/bash
# start_tts.sh — Run the Kokoro TTS container locally (AMD ROCm with CPU fallback)
# Exposes an OpenAI-compatible audio.speech API on the host port set below.

set -eo pipefail

CONTAINER_NAME="tts-service"
PORT=${TTS_PORT:-8880}

# 1. Stop and remove existing container if it exists
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "Stopping and removing existing container: ${CONTAINER_NAME}..."
  docker stop "${CONTAINER_NAME}" || true
  docker rm "${CONTAINER_NAME}" || true
fi

# 2. Attempt to run with ROCm GPU support
echo "Attempting to run Kokoro TTS with AMD ROCm GPU acceleration..."
docker run -d \
  --name "${CONTAINER_NAME}" \
  --device=/dev/kfd \
  --device=/dev/dri \
  --group-add video \
  --group-add render \
  -p "${PORT}:8880" \
  -e HSA_OVERRIDE_GFX_VERSION=10.3.0 \
  -e DEVICE=gpu \
  -e USE_GPU=true \
  --restart unless-stopped \
  ghcr.io/remsky/kokoro-fastapi-rocm:latest

# Wait and verify if the container is running and didn't crash
echo "Waiting for container to initialize..."
sleep 5

if [ "$(docker inspect -f '{{.State.Running}}' "${CONTAINER_NAME}")" = "true" ]; then
  # Check logs for SIGILL or other crash indicators
  if docker logs "${CONTAINER_NAME}" 2>&1 | grep -q -E "illegal instruction|SIGILL|code 132|failed"; then
    echo "⚠️ ROCm container crashed or reported errors. Initiating fallback..."
  else
    echo "✅ Kokoro ROCm container successfully launched on port ${PORT}!"
    exit 0
  fi
else
  echo "⚠️ ROCm container failed to stay running. Initiating fallback..."
fi

# Fallback to CPU container
echo "Stopping failed ROCm container..."
docker stop "${CONTAINER_NAME}" || true
docker rm "${CONTAINER_NAME}" || true

echo "Launching CPU fallback container (ultra-lightweight ONNX CPU)..."
docker run -d \
  --name "${CONTAINER_NAME}" \
  -p "${PORT}:8880" \
  -e DEVICE=cpu \
  -e USE_GPU=false \
  --restart unless-stopped \
  ghcr.io/remsky/kokoro-fastapi-cpu:latest

echo "Waiting for CPU container to initialize..."
sleep 5

if [ "$(docker inspect -f '{{.State.Running}}' "${CONTAINER_NAME}")" = "true" ]; then
  echo "✅ Kokoro CPU container successfully launched on port ${PORT} as fallback!"
  exit 0
else
  echo "❌ Error: CPU fallback container also failed to start!"
  docker logs "${CONTAINER_NAME}" || true
  exit 1
fi
