"""Small shared helpers for the FastAPI backend."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import pandas as pd


def df_to_records(df: Optional[pd.DataFrame], limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Convert a DataFrame to JSON-safe records via pandas' own JSON encoder
    (handles numpy scalar types, NaN -> null, and datetimes correctly)."""
    if df is None or df.empty:
        return []
    frame = df.head(limit) if limit else df
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def chart_data(datasets: Dict[str, pd.DataFrame], spec: Dict[str, Any]) -> Dict[str, Any]:
    """Compute {labels, values, title} for a bar/donut chart from a STAGE_UI_CONFIG chart spec."""
    df = datasets.get(spec["dataset"])
    if df is None or df.empty or spec["column"] not in df.columns:
        return {"labels": [], "values": [], "title": spec.get("title", ""), "type": spec.get("type", "bar")}

    if spec.get("value_column") and spec["value_column"] in df.columns:
        grouped = df.groupby(spec["column"])[spec["value_column"]].mean().round(1).sort_values(ascending=False).head(10)
    else:
        grouped = df[spec["column"]].value_counts().head(10)

    return {
        "labels": [str(x) for x in grouped.index.tolist()],
        "values": [float(v) for v in grouped.values.tolist()],
        "title": spec.get("title", ""),
        "type": spec.get("type", "bar"),
    }


def hitl_candidates(datasets: Dict[str, pd.DataFrame], spec: Optional[Dict[str, Any]], limit: int = 5) -> List[Dict[str, str]]:
    """Compute the HITL approval candidate list from a STAGE_UI_CONFIG hitl spec."""
    if not spec:
        return []
    df = datasets.get(spec["dataset"])
    if df is None or df.empty or spec["match_column"] not in df.columns:
        return []

    match_col = spec["match_column"]
    match_val = spec["match_value"]
    subset = df[df[match_col] == match_val].head(limit)

    candidates = []
    for _, row in subset.iterrows():
        row_dict = row.to_dict()
        try:
            label = spec["label_template"].format(**row_dict)
        except Exception:
            label = str(row_dict.get(spec["id_column"], "item"))
        candidates.append({"id": str(row_dict.get(spec["id_column"], "")), "label": label})
    return candidates
