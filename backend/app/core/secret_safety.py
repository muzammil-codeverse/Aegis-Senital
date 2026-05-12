from __future__ import annotations

import re

OPENAI_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_-]{20,}")
POSTGRES_DSN_PATTERN = re.compile(
    r"((?:postgres|postgresql)(?:\+\w+)?://[^:\s/@]+:)([^@\s/]+)(@)",
    re.IGNORECASE,
)
REDIS_URL_PATTERN = re.compile(
    r"((?:redis|rediss)://(?:[^:@/\s]+:)?)([^@\s/]+)(@)",
    re.IGNORECASE,
)


def sanitize_secret_text(value: str | None) -> str:
    text = str(value or "")
    text = OPENAI_KEY_PATTERN.sub("[redacted]", text)
    text = POSTGRES_DSN_PATTERN.sub(r"\1[redacted]\3", text)
    text = REDIS_URL_PATTERN.sub(r"\1[redacted]\3", text)
    return text


def secret_presence_label(value: str | None) -> str:
    return "PRESENT" if str(value or "").strip() else "MISSING"
