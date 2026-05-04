from __future__ import annotations

import subprocess
import sys

INSTALL_COMMANDS: list[list[str]] = [
    [sys.executable, "-m", "pip", "install", "--no-cache-dir", "insightface"],
    [sys.executable, "-m", "pip", "install", "--no-cache-dir", "faiss-cpu"],
    [sys.executable, "-m", "pip", "install", "--no-cache-dir", "opencv-python"],
    [sys.executable, "-m", "pip", "install", "--no-cache-dir", "torch", "torchvision"],
    [sys.executable, "-m", "pip", "install", "--no-cache-dir", "ultralytics"],
    [sys.executable, "-m", "pip", "install", "--no-cache-dir", "psycopg2-binary", "sqlalchemy", "asyncpg"],
    [sys.executable, "-m", "pip", "install", "--no-cache-dir", "opencv-contrib-python"],
    [sys.executable, "-m", "pip", "install", "--no-cache-dir", "torchreid"],
]


def run_install_sequence() -> None:
    for command in INSTALL_COMMANDS:
        subprocess.run(command, check=True)


def verify_installation() -> None:
    import asyncpg  # noqa: F401
    import cv2  # noqa: F401
    import faiss  # noqa: F401
    import insightface  # noqa: F401
    import psycopg2  # noqa: F401
    import sqlalchemy  # noqa: F401
    import torch  # noqa: F401
    import torchvision  # noqa: F401
    import ultralytics  # noqa: F401
    from torchreid.utils import FeatureExtractor  # noqa: F401


def validate_cuda() -> None:
    import torch

    assert torch.cuda.is_available(), "CUDA not available - inference not allowed"


def main() -> None:
    run_install_sequence()
    verify_installation()
    validate_cuda()
    print("Full stack installation and validation completed successfully.")


if __name__ == "__main__":
    main()
