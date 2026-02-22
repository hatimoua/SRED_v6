import streamlit as st
from sred.ui.api_client import get_client, APIError
from sred.ui.state import get_run_id
from sred.api.schemas.files import FileStatusDTO

st.title("File Uploads")

run_id = get_run_id()
if not run_id:
    st.error("Please select a Run first.")
    st.stop()

client = get_client()

# --- Uploader ---
uploaded_files = st.file_uploader(
    "Upload Documents",
    accept_multiple_files=True,
    type=["csv", "pdf", "docx", "txt", "md", "json"],
)

if uploaded_files:
    # Snapshot existing hashes to detect deduplication
    try:
        existing_hashes = {f.content_hash for f in client.list_files(run_id).items}
    except APIError:
        existing_hashes = set()

    for uf in uploaded_files:
        try:
            content = uf.read()
            file_dto = client.upload_file(
                run_id,
                uf.name,
                content,
                uf.type or "application/octet-stream",
            )
            if file_dto.content_hash in existing_hashes:
                st.toast(f"{uf.name} already uploaded.", icon="\u2139\ufe0f")
            else:
                st.toast(f"Uploaded {uf.name}", icon="\u2705")
        except APIError as e:
            st.error(f"Failed to upload {uf.name}: {e.detail}")

st.divider()

# --- List Files ---
try:
    file_list = client.list_files(run_id)
except APIError as e:
    st.error(f"Failed to load files: {e.detail}")
    st.stop()

files = file_list.items

if not files:
    st.info("No files uploaded.")
else:
    st.write(f"Total Files: {len(files)}")

    for f in files:
        with st.container(border=True):
            c1, c2, c3, c4, c5 = st.columns([3, 1, 1, 1, 2])
            c1.write(f"**{f.original_filename}**")
            c2.write(f.mime_type)
            c3.write(f"{round(f.size_bytes / 1024, 1)} KB")

            status_icon = (
                "\u2705" if f.status == FileStatusDTO.PROCESSED
                else "\u274c" if f.status == FileStatusDTO.ERROR
                else "\u23f3"
            )
            c4.write(f"{status_icon} {f.status.value}")

            if f.status != FileStatusDTO.PROCESSED:
                if c5.button("Process", key=f"proc_{f.id}"):
                    with st.spinner("Processing..."):
                        try:
                            result = client.process_file(run_id, f.id)
                            st.success(f"Done! {result.message}")
                            st.rerun()
                        except APIError as e:
                            st.error(f"Error: {e.detail}")
            else:
                c5.success("Processed")
