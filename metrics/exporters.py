"""metrics/exporters.py – Exporters for TARS metrics engine."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from metrics.collector import MetricsCollector

logger = logging.getLogger(__name__)


def export_json(collector: MetricsCollector, path: Path = Path("tars_metrics.json")) -> None:
    """Export current metrics snapshot to JSON file.

    Args:
        collector: MetricsCollector instance.
        path: Output file path (defaults to tars_metrics.json).
    """
    try:
        data = collector.to_dict()
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.debug("Metrics exported to %s", path)
    except Exception as exc:
        logger.warning("Failed to export metrics to %s: %s", path, exc)
