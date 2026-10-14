"""Stack check page for the Streamlit dashboard."""

import os

import httpx
import streamlit as st

from api import ApiUnavailableError, fetch_health

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
LABELS = {"database": "PostGIS", "redis": "Redis", "worker": "Celery worker"}

st.set_page_config(page_title="BroadbandMap Dashboard")
st.title("BroadbandMap: stack check")

with httpx.Client(base_url=API_BASE_URL, timeout=10) as client:
    try:
        health = fetch_health(client)
    except ApiUnavailableError:
        st.error("✗ The API cannot be reached.")
    else:
        st.success("✓ API")
        for name, up in health.items():
            if up:
                st.success(f"✓ {LABELS[name]}")
            else:
                st.error(f"✗ {LABELS[name]}")
