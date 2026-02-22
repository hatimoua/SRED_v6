import streamlit as st
from sred.ui.api_client import get_client, APIError
from sred.ui.state import get_run_id
from sred.api.schemas.search import SearchQuery, SearchMode

st.title("Search & Discovery")

run_id = get_run_id()
if not run_id:
    st.warning("Select a Run first.")
    st.stop()

client = get_client()

# --- Controls ---
c1, c2 = st.columns([3, 1])
query = c1.text_input("Search Query", placeholder="e.g. 'machine learning research'")
mode_label = c2.selectbox("Mode", ["Hybrid", "FTS Only", "Vector Only"])

if query:
    st.divider()
    with st.spinner(f"Searching ({mode_label})..."):
        try:
            mode = SearchMode(mode_label)
            payload = SearchQuery(query=query, mode=mode, limit=20)
            response = client.search(run_id, payload)

            st.subheader(f"Results ({response.total})")

            for res in response.results:
                with st.container(border=True):
                    st.markdown(
                        f"**{res.filename or 'Unknown'}** \u00b7 _{res.page_info or ''}_ \u00b7 Score: `{res.score:.4f}`"
                    )
                    st.markdown(res.content, unsafe_allow_html=True)
                    st.caption(f"Source: {res.source}")
        except APIError as e:
            st.error(f"Search failed: {e.detail}")
