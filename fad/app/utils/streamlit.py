from typing import List

import streamlit as st


def clear_session_state(keys: List[str] | None = None, starts_with: List[str] | None = None,
                         ends_with: List[str] | None = None) -> None:
    """Clear specific keys from session state."""
    if keys:
        for key in keys:
            if key in st.session_state:
                del st.session_state[key]
    if starts_with:
        for key in list(st.session_state.keys()):
            if any(key.startswith(prefix) for prefix in starts_with):
                del st.session_state[key]
    if ends_with:
        for key in list(st.session_state.keys()):
            if any(key.endswith(suffix) for suffix in ends_with):
                del st.session_state[key]