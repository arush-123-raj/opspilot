import streamlit as st
import requests
import pandas as pd

API_URL = "http://127.0.0.1:8000"

st.set_page_config(page_title="OpsPilot Command Center", page_icon="🚀", layout="wide")
st.title("🚀 OpsPilot Command Center")

if "token" not in st.session_state:
    st.session_state.token = None

with st.sidebar:
    st.header("🔑 Authentication")
    email = st.text_input("Email", value="admin@example.com")
    password = st.text_input("Password", type="password", value="supersecurepassword123")
    
    if st.button("Login"):
        res = requests.post(f"{API_URL}/login", data={"username": email, "password": password})
        if res.status_code == 200:
            st.session_state.token = res.json().get("access_token")
            st.success("Access Granted")
        else:
            st.error("Invalid credentials")
    
    if st.session_state.token and st.button("Logout"):
        st.session_state.token = None
        st.rerun()

if st.session_state.token:
    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    
    # --- NEW: Create Incident Form ---
    with st.expander("➕ Declare New Incident", expanded=False):
        with st.form("new_incident_form"):
            col1, col2 = st.columns(2)
            with col1:
                title = st.text_input("Incident Title", placeholder="e.g., API Gateway 502 Errors")
                severity = st.selectbox("Severity", ["sev-1", "sev-2", "sev-3"])
            with col2:
                desc = st.text_area("Description", placeholder="Details about the outage...")
                service_id = st.number_input("Service ID", min_value=1, value=1)
            
            if st.form_submit_button("🚨 Trigger Alert"):
                res = requests.post(f"{API_URL}/incidents/", headers=headers, json={
                    "title": title, "description": desc, "severity": severity, "service_id": service_id
                })
                if res.status_code == 201:
                    st.success("Incident declared successfully!")
                    st.rerun()
                else:
                    st.error(f"Failed to declare incident: {res.text}")

    # --- UPDATED: Incident Table & Resolver ---
    st.subheader("📋 Active Incidents")
    response = requests.get(f"{API_URL}/incidents/", headers=headers)
    
    if response.status_code == 200:
        incidents = response.json()
        if incidents:
            df = pd.DataFrame(incidents)[["id", "title", "severity", "status", "created_at"]]
            
            def highlight_row(row):
                if row['status'] == 'resolved':
                    return ['color: gray; font-style: italic'] * len(row)
                if row['severity'] == 'sev-1':
                    return ['background-color: #ff4b4b; color: white; font-weight: bold'] * len(row)
                return [''] * len(row)
                
            st.dataframe(df.style.apply(highlight_row, axis=1), width='stretch')
            
            # --- NEW: Quick Resolve Feature ---
            active_ids = [i['id'] for i in incidents if i['status'] != 'resolved']
            if active_ids:
                st.write("### ✅ Quick Resolve")
                with st.form("resolve_form"):
                    col1, col2, col3 = st.columns([2, 1, 3])
                    with col1:
                        resolve_id = st.selectbox("Incident ID", active_ids, label_visibility="collapsed")
                    with col2:
                        if st.form_submit_button("Mark as Resolved"):
                            res = requests.patch(f"{API_URL}/incidents/{resolve_id}", headers=headers, json={"status": "resolved"})
                            if res.status_code == 200:
                                st.rerun()
        else:
            st.success("No incidents found. All systems operational! 🟢")
            
    if st.button("🔄 Refresh Data"):
        st.rerun()
else:
    st.info("👈 Please log in using the sidebar to access the dashboard.")
