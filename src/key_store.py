"""Client-side API key persistence via browser localStorage.

Uses a JS redirect-with-query-param approach to safely load keys
into the Python backend without component lifecycle issues.
"""

import json
from urllib.parse import unquote
import streamlit as st
import streamlit.components.v1 as components

LS_KEY = "yt_summarizer_keys"


def inject_persistence_script():
    """Inject JS at page top to auto-load saved keys via query param redirect."""
    st.markdown(f"""
    <script>
    (function() {{
        if (window.__yt_keys_done) return;
        window.__yt_keys_done = true;
        var params = new URLSearchParams(window.location.search);
        if (params.get('_yl')) return;  // already loaded, will be cleaned by Python
        var keys = localStorage.getItem('{LS_KEY}');
        if (!keys) return;
        if (sessionStorage.getItem('_yt_keys_sent')) return;
        sessionStorage.setItem('_yt_keys_sent', '1');
        var encoded = encodeURIComponent(keys);
        params.set('_yl', encoded);
        window.location.search = params.toString();
    }})();
    </script>
    """, unsafe_allow_html=True)


def handle_loaded_keys():
    """If keys were loaded via query param, apply them and clean up."""
    raw = st.query_params.get_all("_yl")
    if raw:
        from urllib.parse import unquote
        try:
            keys = json.loads(unquote(raw[0]))
            if isinstance(keys, dict):
                for k, v in keys.items():
                    if v and k not in st.session_state or not st.session_state.get(k):
                        st.session_state[k] = v
        except Exception:
            pass
        st.query_params.pop("_yl")


def save_keys_to_localstorage(keys: dict):
    keys_serialized = json.dumps(keys)
    components.html(f"""
    <script>
    try {{
        localStorage.setItem('{LS_KEY}', '{keys_serialized}');
        sessionStorage.removeItem('_yt_keys_sent');
    }} catch(e) {{}}
    </script>
    """, height=0)


def collect_provider_keys() -> dict:
    keys = {}
    for k in ("custom_api_key", "custom_go_api_key", "whisper_openai_key",
              "provider_key_stability-ai", "provider_key_replicate", "provider_key_pruna"):
        v = st.session_state.get(k, "")
        if v.strip():
            keys[k] = v.strip()
    return keys


def _valid_key_names() -> set:
    return {"custom_api_key", "custom_go_api_key", "whisper_openai_key",
            "provider_key_stability-ai", "provider_key_replicate", "provider_key_pruna"}


def export_keys_json() -> str:
    """Export all keys as a JSON string (for file download)."""
    keys = collect_provider_keys()
    return json.dumps(keys, indent=2)


def import_keys_from_json(json_str: str) -> dict:
    """Parse and validate an exported keys JSON file. Returns {key: value, ...}."""
    data = json.loads(json_str)
    if not isinstance(data, dict):
        raise ValueError("Format invalide : objet JSON attendu")
    valid_keys = _valid_key_names()
    result = {}
    for k, v in data.items():
        if k in valid_keys and isinstance(v, str) and v.strip():
            result[k] = v.strip()
    return result


def apply_imported_keys(keys: dict):
    """Apply imported keys to st.session_state AND persist to localStorage."""
    for k, v in keys.items():
        st.session_state[k] = v
    save_keys_to_localstorage(keys)
