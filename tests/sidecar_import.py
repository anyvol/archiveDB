"""Load sidecar services without colliding on the bare module name ``main``."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


def load_sidecar(module_name: str, relative_main: str) -> ModuleType:
    """Import ``backup/main.py`` / ``ocr/main.py`` under a unique sys.modules key.

    Several sidecars expose a top-level ``main.py``. Path inserts + ``import main``
    collide across tests (alphabetically backup runs before OCR and caches the wrong
    module). Loading by file path with a unique name avoids that.
    """
    if module_name in sys.modules:
        return sys.modules[module_name]

    path = ROOT / relative_main
    package_dir = str(path.parent)
    if package_dir not in sys.path:
        sys.path.insert(0, package_dir)

    # Drop a stale bare ``main`` from another sidecar so ``pipeline.*`` / relative
    # imports inside this file never see the wrong module object.
    stale = sys.modules.get("main")
    if stale is not None:
        stale_file = getattr(stale, "__file__", None)
        if stale_file and Path(stale_file).resolve() != path.resolve():
            del sys.modules["main"]

    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
