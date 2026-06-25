from __future__ import annotations

import os
import shutil
from pathlib import Path


def _patch_fast_langdetect_small_model_path() -> None:
    cache_dir = os.getenv("FAST_LANGDETECT_RESOURCE_CACHE", "").strip()
    if not cache_dir:
        return

    try:
        import fast_langdetect.ft_detect.infer as infer
    except Exception:
        return

    try:
        source = Path(infer.LOCAL_SMALL_MODEL_PATH)
        target_dir = Path(cache_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / source.name
        if source.exists() and (not target.exists() or target.stat().st_size != source.stat().st_size):
            shutil.copy2(source, target)
        if target.exists():
            infer.LOCAL_SMALL_MODEL_PATH = target
    except Exception:
        return


_patch_fast_langdetect_small_model_path()
