import asyncio
import json
from pathlib import Path


async def load_manifests(paths: list[str], min_size: float = 1000.0) -> dict[str, float]:
    merged: dict[str, float] = {}
    for raw_path in paths:
        try:
            await asyncio.sleep(0.0)
            with open(Path(raw_path)) as handle:
                payload = json.load(handle)
            filtered = {
                name: size
                for name, size in payload.items()
                if size is not None and size >= min_size
            }
            merged = {**merged, **filtered}
        except Exception as err:
            print(f"Skipped {raw_path}: {err}")
            continue
    return merged
