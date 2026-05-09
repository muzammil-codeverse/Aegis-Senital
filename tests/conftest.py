from __future__ import annotations

import sys
from pathlib import Path
import importlib


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"

for path in (str(ROOT), str(BACKEND)):
    if path not in sys.path:
        sys.path.insert(0, path)


def _is_repo_module(module) -> bool:
    module_file = getattr(module, "__file__", "") or ""
    return bool(module_file) and str(ROOT).lower() in module_file.lower()


existing_ml = sys.modules.get("ml")
if existing_ml is not None and not _is_repo_module(existing_ml):
    for key in list(sys.modules.keys()):
        if key == "ml" or key.startswith("ml."):
            sys.modules.pop(key, None)

importlib.import_module("ml.runtime")
