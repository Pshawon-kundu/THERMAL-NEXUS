"""Group-aware cross-validation helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
from sklearn.model_selection import GroupKFold, StratifiedGroupKFold


def make_group_folds(
    features: pd.DataFrame,
    target: pd.Series,
    groups: pd.Series,
    n_splits: int,
    random_seed: int,
) -> tuple[list[tuple[list[int], list[int]]], dict[str, Any]]:
    """Create deterministic group-aware folds and a zero-overlap report."""

    unique_group_count = groups.nunique()
    actual_splits = min(n_splits, unique_group_count)
    fallback = False
    try:
        splitter = StratifiedGroupKFold(
            n_splits=actual_splits, shuffle=True, random_state=random_seed
        )
        raw_folds = list(splitter.split(features, target, groups))
        strategy = "StratifiedGroupKFold"
    except ValueError:
        fallback = True
        splitter = GroupKFold(n_splits=actual_splits)
        raw_folds = list(splitter.split(features, target, groups))
        strategy = "GroupKFold"

    folds = [(train.tolist(), validation.tolist()) for train, validation in raw_folds]
    report = _fold_report(folds, target, groups, strategy, fallback)
    return folds, report


def write_group_cv_report(report: dict[str, Any], output_dir: Path) -> None:
    """Write group CV evidence."""

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "group_cv_report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    lines = [
        "# Group CV Report",
        "",
        f"Strategy: `{report['strategy']}`",
        f"Fallback used: `{report['fallback_used']}`",
        f"Fold count: {len(report['folds'])}",
        "",
        "## Fold Overlap",
        "",
    ]
    lines.extend(
        f"- Fold {fold['fold']}: overlap={fold['overlap_count']}, "
        f"train_runs={fold['train_run_count']}, "
        f"validation_runs={fold['validation_run_count']}"
        for fold in report["folds"]
    )
    (output_dir / "group_cv_report.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def _fold_report(
    folds: list[tuple[list[int], list[int]]],
    target: pd.Series,
    groups: pd.Series,
    strategy: str,
    fallback: bool,
) -> dict[str, Any]:
    report_folds = []
    all_validation_runs: set[str] = set()
    for index, (train_idx, validation_idx) in enumerate(folds):
        train_runs = set(groups.iloc[train_idx])
        validation_runs = set(groups.iloc[validation_idx])
        overlap = train_runs & validation_runs
        all_validation_runs |= validation_runs
        report_folds.append(
            {
                "fold": index,
                "train_run_count": len(train_runs),
                "validation_run_count": len(validation_runs),
                "overlap_count": len(overlap),
                "overlap_runs": sorted(overlap),
                "validation_class_counts": {
                    str(k): int(v)
                    for k, v in target.iloc[validation_idx].value_counts().items()
                },
            }
        )
    return {
        "strategy": strategy,
        "fallback_used": fallback,
        "zero_run_overlap": all(fold["overlap_count"] == 0 for fold in report_folds),
        "all_training_runs_seen_in_validation": (
            set(groups.unique()) == all_validation_runs
        ),
        "folds": report_folds,
    }
