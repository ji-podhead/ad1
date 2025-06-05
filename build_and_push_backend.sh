#!/bin/bash
# build_and_push_backend.sh
# Usage: ./build_and_push_backend.sh <tagname>

set -e

DOCKERFILE_PATH="build/Dockerfile.backend"
CONTEXT_DIR="."

if [ -z "$1" ]; then
  echo "Usage: $0 <tagname>"
  exit 1
fi

TAG=$1
FULL_IMAGE_NAME="orchestranexus/agentbox:$TAG"

echo "[+] Building backend image: $FULL_IMAGE_NAME"
docker build -f $DOCKERFILE_PATH -t $FULL_IMAGE_NAME $CONTEXT_DIR

echo "[+] Pushing backend image: $FULL_IMAGE_NAME"
docker push $FULL_IMAGE_NAME

echo "[i] Update your docker-compose.yml to use image: $FULL_IMAGE_NAME for the backend service."
