"""Command-line entry points for the external T15 benchmark phase."""

from __future__ import annotations

import argparse
import json
from typing import Any

from ml.external_t15.dataset import audit_dataset, build_model_ready_datasets
from ml.external_t15.modeling import (
    evaluate_external_models,
    train_external_models,
    verify_external_phase,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="External T15 benchmark workflow")
    parser.add_argument(
        "command", choices=("audit", "build", "train", "evaluate", "verify", "all")
    )
    args = parser.parse_args()
    result: dict[str, Any] = {}
    if args.command in {"audit", "all"}:
        result["audit"] = audit_dataset()
    if args.command in {"build", "all"}:
        result["build"] = build_model_ready_datasets()
    if args.command in {"train", "all"}:
        result["train"] = train_external_models()
    if args.command in {"evaluate", "all"}:
        result["evaluate"] = evaluate_external_models()
    if args.command in {"verify", "all"}:
        result["verify"] = verify_external_phase()
    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
