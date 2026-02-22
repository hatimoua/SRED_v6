"""Session-state helpers for the Streamlit UI.

No ORM, no DB — only reads/writes ``st.session_state``.
"""
import streamlit as st
from typing import Optional


def init_session() -> None:
    """Initialize session state variables."""
    if "run_id" not in st.session_state:
        st.session_state["run_id"] = None


def get_run_id() -> Optional[int]:
    """Get currently selected run ID."""
    return st.session_state.get("run_id")


def set_run_id(run_id: int) -> None:
    """Set currently selected run ID."""
    st.session_state["run_id"] = run_id


def get_current_run_name() -> str:
    """Get name of current run, or empty string."""
    return st.session_state.get("run_name", "")


def set_run_context(run_id: int, run_name: str) -> None:
    """Set context from run id and name (DTO-friendly)."""
    st.session_state["run_id"] = run_id
    st.session_state["run_name"] = run_name
