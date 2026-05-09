# GPU Runtime Guide

## Prerequisites
- NVIDIA GPU with CUDA support
- NVIDIA Container Toolkit installed
  - Installation: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html
- Docker 19.03+ or Docker Compose v2

## Running with GPU

```
docker compose -f docker-compose.yml -f docker-compose.gpu.yml --env-file .env.docker up --build
```

## Open-Vocab Model with GPU

1. Download Grounding DINO weights locally.
2. Set in .env.docker:
   ```
   AEGIS_OPEN_VOCAB_MODEL_PATH=/app/models/grounding_dino
   AEGIS_OPEN_VOCAB_PROCESSOR_PATH=/app/models/grounding_dino
   AEGIS_DEVICE_PREFERENCE=cuda
   ```
3. Mount the model directory: add `./models/grounding_dino:/app/models/grounding_dino` to backend volumes.
4. Use the Admin UI to trigger model load: Open-Vocab Scanner -> Model Control -> Load.

## Verification
Check GPU is detected:
```
docker exec aegis-backend python -c "import torch; print(torch.cuda.is_available())"
```
