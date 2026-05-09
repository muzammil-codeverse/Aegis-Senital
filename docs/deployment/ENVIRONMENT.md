# Environment Variables Reference

## Required in Production
| Variable | Description |
|----------|-------------|
| AEGIS_JWT_SECRET | JWT signing secret — must be 32+ random characters |
| AEGIS_BOOTSTRAP_ADMIN_PASSWORD | Initial admin password |

## Optional
| Variable | Default | Description |
|----------|---------|-------------|
| APP_ENV | dev | Environment: dev, staging, production |
| POSTGRES_DSN | (empty) | PostgreSQL connection string; SQLite fallback if not set |
| REDIS_URL | (empty) | Redis connection URL; in-memory fallback if not set |
| AEGIS_DEVICE_PREFERENCE | auto | Device: auto, cuda, cpu |
| AEGIS_OPEN_VOCAB_PROVIDER | grounding_dino | Open-vocab model provider |
| AEGIS_OPEN_VOCAB_MODEL_PATH | (empty) | Local path to Grounding DINO model weights |
| AEGIS_OPEN_VOCAB_PROCESSOR_PATH | (empty) | Local path to Grounding DINO processor |
| AEGIS_OPEN_VOCAB_ALLOW_DOWNLOAD | false | Allow downloading weights from HuggingFace |
| VITE_API_BASE_URL | http://localhost:8000 | Frontend API base URL |
| VITE_WS_BASE_URL | ws://localhost:8000 | Frontend WebSocket base URL |

## Security Warning
- Never commit real JWT secrets or passwords.
- Use strong random values for AEGIS_JWT_SECRET (32+ chars).
- Rotate secrets on any suspected exposure.
