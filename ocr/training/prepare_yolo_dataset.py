#!/usr/bin/env python3
"""Convert archiveDB OCR dataset ZIP → YOLO detection dataset (stamp class)."""

from __future__ import annotations

import argparse
import json
import random
import shutil
import zipfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", required=True, help="Path to exported dataset ZIP")
    parser.add_argument("--out", required=True, help="Output directory for YOLO dataset")
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    zip_path = Path(args.zip)
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    images_train = out / "images" / "train"
    images_val = out / "images" / "val"
    labels_train = out / "labels" / "train"
    labels_val = out / "labels" / "val"
    for d in (images_train, images_val, labels_train, labels_val):
        d.mkdir(parents=True, exist_ok=True)

    extract_dir = out / "_extract"
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_dir)

    samples: list[tuple[Path, Path, list[float]]] = []
    for labels_json in extract_dir.rglob("labels.json"):
        sample_dir = labels_json.parent
        page = sample_dir / "page.png"
        if not page.is_file():
            # Fall back: cannot place stamp on page without page image
            continue
        data = json.loads(labels_json.read_text(encoding="utf-8"))
        roi = data.get("stamp_roi_norm")
        if not roi or len(roi) != 4:
            continue
        samples.append((page, labels_json, [float(v) for v in roi]))

    if not samples:
        raise SystemExit(
            "No samples with page.png + stamp_roi_norm found. "
            "Annotate stamp region on the page and re-export."
        )

    random.Random(args.seed).shuffle(samples)
    n_val = max(1, int(len(samples) * args.val_ratio)) if len(samples) > 4 else max(0, len(samples) // 5)
    val_set = set(range(n_val))

    for i, (page, _lj, roi) in enumerate(samples):
        split = "val" if i in val_set else "train"
        stem = f"job_{page.parent.name}_{i}"
        img_dst = out / "images" / split / f"{stem}.png"
        lbl_dst = out / "labels" / split / f"{stem}.txt"
        shutil.copy2(page, img_dst)
        # YOLO: class cx cy w h (normalized)
        x0, y0, x1, y1 = roi
        cx = (x0 + x1) / 2.0
        cy = (y0 + y1) / 2.0
        bw = max(1e-6, x1 - x0)
        bh = max(1e-6, y1 - y0)
        lbl_dst.write_text(f"0 {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}\n", encoding="utf-8")

    data_yaml = out / "data.yaml"
    data_yaml.write_text(
        (
            f"path: {out.resolve()}\n"
            "train: images/train\n"
            "val: images/val\n"
            "names:\n"
            "  0: stamp\n"
        ),
        encoding="utf-8",
    )
    print(f"Prepared {len(samples)} samples → {out}")
    print(f"data.yaml: {data_yaml}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
