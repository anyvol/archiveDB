#!/usr/bin/env python3
"""Train a YOLO stamp detector and optionally log to MLflow."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, help="Path to data.yaml from prepare_yolo_dataset.py")
    parser.add_argument("--model", default="yolov8n.pt")
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--imgsz", type=int, default=1280)
    parser.add_argument("--project", default="./runs/stamp")
    parser.add_argument("--name", default="detect")
    parser.add_argument("--mlflow-uri", default="")
    parser.add_argument("--device", default="")
    args = parser.parse_args()

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit(
            "ultralytics is required: pip install ultralytics\n"
            f"Import error: {exc}"
        ) from exc

    mlflow = None
    if args.mlflow_uri:
        try:
            import mlflow

            mlflow.set_tracking_uri(args.mlflow_uri)
            mlflow.set_experiment("archivedb-stamp-detector")
            mlflow.start_run(run_name=args.name)
            mlflow.log_params(
                {
                    "model": args.model,
                    "epochs": args.epochs,
                    "imgsz": args.imgsz,
                    "data": str(Path(args.data).resolve()),
                }
            )
        except Exception as exc:
            print(f"MLflow logging disabled: {exc}")
            mlflow = None

    model = YOLO(args.model)
    train_kwargs = {
        "data": args.data,
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "project": args.project,
        "name": args.name,
        "exist_ok": True,
    }
    if args.device:
        train_kwargs["device"] = args.device
    results = model.train(**train_kwargs)

    best = Path(args.project) / args.name / "weights" / "best.pt"
    print(f"Best weights: {best}")
    if mlflow is not None:
        try:
            if best.is_file():
                mlflow.log_artifact(str(best))
            metrics = getattr(results, "results_dict", None) or {}
            for k, v in list(metrics.items())[:20]:
                if isinstance(v, (int, float)):
                    mlflow.log_metric(str(k).replace("(", "_").replace(")", ""), float(v))
            mlflow.end_run()
        except Exception as exc:
            print(f"MLflow finalize warning: {exc}")

    deploy_hint = (
        "\nDeploy:\n"
        f"  cp {best} ./models/stamp_detector.pt\n"
        "  # docker-compose ocr service:\n"
        "  #   OCR_STAMP_DETECTOR_PATH=/models/stamp_detector.pt\n"
        "  #   volumes: ./models:/models:ro\n"
    )
    print(deploy_hint)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
