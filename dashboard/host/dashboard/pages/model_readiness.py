"""Model Readiness tab — embedded deployment manifest JSON."""

from __future__ import annotations

from pathlib import Path

import streamlit as st


def render() -> None:
    """Render the embedded deployment manifest JSON."""
    st.markdown("### Model and Embedded Readiness")
    manifest = Path("embedded/generated/deployment_manifest.json")
    if manifest.exists():
        st.json(manifest.read_text(encoding="utf-8"))
    else:
        st.info("Embedded manifest has not been generated.")