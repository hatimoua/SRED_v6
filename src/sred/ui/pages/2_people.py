import streamlit as st
from sred.ui.api_client import get_client, APIError
from sred.ui.state import get_run_id
from sred.api.schemas.people import PersonCreate, PersonUpdate, RateStatusDTO

st.title("People & Roles")

run_id = get_run_id()
if not run_id:
    st.error("Please select a Run first.")
    st.stop()

client = get_client()

# --- Add Person ---
with st.expander("Add Person", expanded=False):
    with st.form("add_person"):
        name = st.text_input("Name (Required)")
        role = st.text_input("Role (Required)")
        rate = st.number_input("Hourly Rate ($)", min_value=0.0, step=1.0, value=0.0)

        submitted = st.form_submit_button("Add Person")
        if submitted:
            if not name or not role:
                st.error("Name and Role are required.")
            else:
                try:
                    payload = PersonCreate(
                        name=name, role=role,
                        hourly_rate=rate if rate > 0 else None,
                    )
                    client.create_person(run_id, payload)
                    st.success(f"Added {name}.")
                    st.rerun()
                except APIError as e:
                    st.error(f"Failed: {e.detail}")

st.divider()

# --- List People ---
try:
    people_list = client.list_people(run_id)
except APIError as e:
    st.error(f"Failed to load people: {e.detail}")
    st.stop()

people = people_list.items

pending_rates = [p for p in people if p.rate_status == RateStatusDTO.PENDING]
if pending_rates:
    st.warning(f"{len(pending_rates)} people have PENDING rates. This will block claim generation.")

if not people:
    st.info("No people added yet.")
else:
    for p in people:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 3, 2, 2])
            c1.write(f"**{p.name}**")
            c2.write(f"_{p.role}_")

            rate_str = f"${p.hourly_rate}" if p.hourly_rate else "Pending"
            c3.write(f"Rate: {rate_str}")

            if p.rate_status == RateStatusDTO.PENDING:
                new_rate = c4.number_input("Set Rate", min_value=0.0, key=f"rate_{p.id}")
                if c4.button("Save", key=f"save_{p.id}"):
                    if new_rate > 0:
                        try:
                            client.update_person(run_id, p.id, PersonUpdate(hourly_rate=new_rate))
                            st.rerun()
                        except APIError as e:
                            st.error(f"Failed: {e.detail}")
            else:
                c4.success("Rate Set")
