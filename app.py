import os
import sys
import asyncio

# --------------------------------------------------
# SYSTEM CONFIG FOR CLOUD PLAYWRIGHT 
# --------------------------------------------------
# Windows Asyncio Fix
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# Force Playwright browser install on Streamlit Community Cloud
os.system("playwright install chromium")

import streamlit as st
import pandas as pd
import datetime
import urllib.parse
import gspread
from google.oauth2.service_account import Credentials
from attendance_bot import run_swipe_for_date

# --------------------------------------------------
# PAGE CONFIG & CSS
# --------------------------------------------------

st.set_page_config(page_title="Dashboard", page_icon="💼", layout="centered", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    .main { padding-top: 1rem; }
    .block-container { max-width: 700px; padding-left: 1rem; padding-right: 1rem; }
    h1 { text-align: left; margin-bottom: 0.2rem; }
    .subtitle { text-align: left; color: #666; margin-bottom: 1.5rem; }
    .section-title { font-size: 1.15rem; font-weight: 600; margin-top: 1.5rem; margin-bottom: 0.8rem; }
    div.stButton > button { width: 100%; height: 3rem; font-size: 1rem; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

# --------------------------------------------------
# LOAD STUDENT DATABASE
# --------------------------------------------------

STUDENTS = {
    "26-0313": ["Hrishikesh Chowdhury", "Playgroup"],
    "26-0392": ["Arpan Das", "Playgroup"],
    "26-0316": ["Aahan Bose", "Playgroup"],
    "26-0241": ["Agnimitra Mondal", "Nursery"],
    "26-0562": ["Jainikka Raj Sharma", "Sr. KG"],
    "26-0560": ["Sannvi Maity", "Nursery"],
    "26-0559": ["Souronil Sardar", "Playgroup"],
    "26-0553": ["Mihsan Gazi", "Nursery"],
    "26-0557": ["Avyan Ghosh", "Playgroup"],
    "26-0522": ["Prayushi Adak", "Nursery"],
    "26-0561": ["Ankur Mondal", "Nursery"],
    "NIL": ["NIL", "NIL"]
}

# --------------------------------------------------
# CACHED GLOBAL PAYMENTS
# --------------------------------------------------

@st.cache_resource
def get_global_payments():
    return []

payments_cache = get_global_payments()

def append_payment(record: dict):
    payments_cache.append(record)

def get_payments_df():
    return pd.DataFrame(payments_cache)

def delete_payment_by_created_at(created_at_value: str):
    payments_cache[:] = [p for p in payments_cache if p.get("created_at") != created_at_value]

def clear_all_payments():
    payments_cache.clear()

# --------------------------------------------------
# GOOGLE SHEETS AUTOMATION
# --------------------------------------------------

GSHEET_URL = "https://docs.google.com/spreadsheets/d/15dzIujFQ0xx6zqVYkb9phEGndPfucjkttjef4QcBncg/edit"

def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    return gspread.authorize(credentials)

def update_dcr_gsheet(new_data_df):
    try:
        client = get_gspread_client()
        spreadsheet = client.open_by_url(GSHEET_URL)
        ws = spreadsheet.worksheet("DCR")
        
        existing_data = ws.get_all_values()
        existing_txns = set()
        last_sl = 0
        
        for row in existing_data[1:]:  
            if len(row) >= 16:
                txn = str(row[15]).strip()
                if txn: existing_txns.add(txn)
            if len(row) >= 1:
                try:
                    sl = int(row[0])
                    if sl > last_sl: last_sl = sl
                except ValueError:
                    pass
                    
        rows_to_append = []
        
        for _, row_data in new_data_df.iterrows():
            txn_id = str(row_data.get('transaction_id', '')).strip()
            if txn_id in existing_txns and txn_id not in ['nan', '']:
                continue
                
            last_sl += 1
            
            date_val = str(row_data.get('date', ''))
            if date_val and date_val != 'nan':
                try: date_val = pd.to_datetime(date_val).strftime('%d-%m-%Y')
                except: pass
            else: date_val = ''
            
            cash_dep = str(row_data.get('cash_deposit_date', ''))
            if cash_dep and cash_dep != 'nan':
                try: cash_dep = pd.to_datetime(cash_dep).strftime('%d-%m-%Y')
                except: pass
            else: cash_dep = ''

            sid = str(row_data.get('student_id', '')).strip()
            sname = str(row_data.get('student_name', '')).strip()
            sclass = str(row_data.get('class', '')).strip()
            if sid.upper() == 'NIL' and sname.upper() == 'NIL' and sclass.upper() == 'NIL':
                row_values = [
                    last_sl, 'NEW GARIA', '', '', '', 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 
                    '', date_val, '', '', '', 'NILL'
                ]
            else:
                row_values = [
                    last_sl, 'NEW GARIA', row_data.get('student_id', ''), row_data.get('student_name', ''),
                    row_data.get('class', ''), float(row_data.get('registration_fee', 0)),
                    float(row_data.get('admission_fee', 0)), float(row_data.get('tuition_fee', 0)),
                    float(row_data.get('kits_fee', 0)), float(row_data.get('late_fee', 0)),
                    float(row_data.get('amount', 0)), row_data.get('payment_mode', ''),
                    date_val, cash_dep, row_data.get('collector_bank', ''), txn_id, row_data.get('remarks', '')
                ]
            
            row_values = ["" if str(v) == "nan" else v for v in row_values]
            rows_to_append.append(row_values)
            existing_txns.add(txn_id)
            
        if rows_to_append:
            ws.append_rows(rows_to_append, value_input_option='USER_ENTERED')
            return f"Successfully added {len(rows_to_append)} new records to Google Sheets!"
        else:
            return "No new unique records to add."
            
    except Exception as e:
        return f"Google Sheets Error: {e}"

if "form_counter" not in st.session_state: 
    st.session_state["form_counter"] = 0

def _k(name: str) -> str: 
    return f"{name}_{st.session_state['form_counter']}"

# --------------------------------------------------
# HEADER & TABS
# --------------------------------------------------

left, right = st.columns([8, 2])
with left:
    st.title("💼 Management Dashboard")
    st.markdown('<div class="subtitle">Fee Collection & Daily Attendance</div>', unsafe_allow_html=True)
with right:
    if st.button("New Day", key="new_day"):
        clear_all_payments()
        st.rerun()

add_tab, review_tab, attendance_tab = st.tabs(["Add Payment", "Review Collection", "Attendance Swipe"])

# --------------------------------------------------
# TAB 1: ADD PAYMENT
# --------------------------------------------------
with add_tab:
    # --- ADD THIS BLOCK ---
    if st.session_state.get("payment_success"):
        st.success("✅ Payment details captured and saved successfully!")
        st.session_state["payment_success"] = False  # Reset so it only shows once
    # ----------------------
    
    st.markdown('<div class="section-title">Payment Details</div>', unsafe_allow_html=True)
    payment_date = st.date_input("Date", key=_k("payment_date"))

    student_options = [f"{sid} - {STUDENTS[sid][0]}" for sid in sorted(STUDENTS.keys())]
    selected_option = st.selectbox("Student (ID - Name)", ["-- Select student --"] + student_options, key=_k("selected_student"))

    student_id = ""
    student_class = ""
    selected_student = ""
    if selected_option and selected_option != "-- Select student --":
        student_id = selected_option.split(" - ")[0]
        selected_student = STUDENTS.get(student_id, ["", ""])[0]
        student_class = STUDENTS.get(student_id, ["", ""])[1]

    st.text_input("Student ID", value=str(student_id), disabled=True)
    st.text_input("Class", value=str(student_class), disabled=True)

    st.markdown('<div class="section-title">Fee Details</div>', unsafe_allow_html=True)
    def _parse_fee_input(label: str, key: str) -> float:
        raw = st.text_input(label, value="", placeholder="0.00", key=_k(key))
        raw = (raw or "").strip()
        if raw == "": return 0.0
        try: return float(raw)
        except ValueError:
            st.warning(f"Invalid amount entered for '{label}'. Using 0.00")
            return 0.0

    registration_fee = _parse_fee_input("Registration Fee Received (₹)", "registration_fee")
    admission_fee = _parse_fee_input("Admission Fee Received (₹)", "admission_fee")
    tuition_fee = _parse_fee_input("Tuition Fee Received (₹)", "tuition_fee")
    kits_fee = _parse_fee_input("Kits Fee Received (₹)", "kits_fee")
    late_fee = _parse_fee_input("Late Fee Received (₹)", "late_fee")

    st.markdown('<div class="section-title">Payment Information</div>', unsafe_allow_html=True)
    payment_mode = st.selectbox("Mode of Payment", ["UPI", "Bank Transfer", "Cash", "Cheque", "Other"], key=_k("payment_mode"))
    
    cash_deposit_date = None
    if payment_mode == "Cash":
        cash_deposit_date = st.date_input("Cash Deposit Date", key=_k("cash_deposit_date"))

    collector_bank = st.text_input("Collector Bank", placeholder="Enter collector bank", key=_k("collector_bank"))
    transaction_id = st.text_input("Transaction ID", placeholder="Enter transaction ID", key=_k("transaction_id"))
    remarks = st.text_area("Remarks (if any)", placeholder="Enter remarks", height=100, key=_k("remarks"))

    total_fee = registration_fee + admission_fee + tuition_fee + kits_fee + late_fee

    st.markdown(
        f"""
        <div style="padding: 15px; border-radius: 10px; background-color: #f5f5f5; margin-top: 10px; margin-bottom: 20px; text-align: center;">
            <div style="font-size: 0.9rem; color: #666;">Total Payment</div>
            <div style="font-size: 1.6rem; font-weight: 700;">₹{total_fee:,.2f}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if st.button("SUBMIT PAYMENT", type="primary", key="submit_payment_btn"):
        is_nil_entry = False
        try:
            is_nil_entry = (
                str(student_id).strip().upper() == 'NIL' and
                str(student_class).strip().upper() == 'NIL' and
                str(selected_student).strip().upper() == 'NIL'
            )
        except Exception:
            is_nil_entry = False

        if not selected_student:
            st.error("Please select a student.")
        elif total_fee <= 0 and not is_nil_entry:
            st.error("Please enter at least one fee amount.")
        elif not (str(transaction_id).strip()) and not is_nil_entry:
            st.error("Transaction ID is required.")
        else:
            payment_data = {
                "date": str(payment_date), "student_name": selected_student, "student_id": student_id,
                "class": student_class, "registration_fee": registration_fee, "admission_fee": admission_fee,
                "tuition_fee": tuition_fee, "kits_fee": kits_fee, "late_fee": late_fee, "amount": total_fee,
                "payment_mode": payment_mode, "cash_deposit_date": (str(cash_deposit_date) if cash_deposit_date else ""),
                "collector_bank": collector_bank, "transaction_id": transaction_id,
                "remarks": remarks, "created_at": datetime.datetime.now().isoformat()
            }
            append_payment(payment_data)
            st.session_state["payment_success"] = True  
            st.session_state["form_counter"] += 1
            st.rerun()

# --------------------------------------------------
# TAB 2: REVIEW COLLECTION
# --------------------------------------------------
with review_tab:
    st.markdown('<div class="section-title">Today\'s Collections</div>', unsafe_allow_html=True)
    payments_df = get_payments_df()
    today_str = str(datetime.date.today())

    if payments_df.empty:
        st.info("No payments recorded yet.")
    else:
        today_df = payments_df[payments_df["date"] == today_str].copy()
        if today_df.empty:
            st.info("No payments recorded for today.")
        else:
            fee_cols = ["registration_fee", "admission_fee", "tuition_fee", "kits_fee", "late_fee"]
            for col in fee_cols: today_df[col] = pd.to_numeric(today_df.get(col, 0), errors="coerce").fillna(0.0)

            today_df["amount"] = today_df[fee_cols].sum(axis=1)
            total_today = today_df["amount"].sum()

            for i, row in today_df.reset_index().iterrows():
                cols = st.columns([3, 1])
                with cols[0]:
                    st.markdown(f"**{row.get('student_name','')}** — ₹{row.get('amount',0):,.2f} — {row.get('payment_mode','')}")
                    st.write(f"Bank: {row.get('collector_bank','')} | TXN: {row.get('transaction_id','')} | Remarks: {row.get('remarks','')}")
                with cols[1]:
                    created_at_val = row.get("created_at")
                    st.button("Delete", key=f"del_{i}", on_click=delete_payment_by_created_at, args=(created_at_val,))

            st.markdown(f"**Total collected today:** ₹{total_today:,.2f}")

            if st.button("Sync with Google Sheets", type="primary", key="sync_gsheets"):
                with st.spinner("Syncing with Google Sheets..."):
                    gsheet_status = update_dcr_gsheet(today_df)
                    if "Error" in gsheet_status: 
                        st.error(gsheet_status)
                    else: 
                        st.success(gsheet_status)

# --------------------------------------------------
# TAB 3: ATTENDANCE SWIPE
# --------------------------------------------------
with attendance_tab:
    st.markdown('<div class="section-title">Spine HR Attendance Automation</div>', unsafe_allow_html=True)
    
    # Fetch credentials directly from .streamlit/secrets.toml (or Streamlit Cloud Secrets)
    emp_user = st.secrets.get("SPINE_USER", "")
    emp_pass = st.secrets.get("SPINE_PASS", "")

    # Date selection
    today_date = datetime.date.today()
    selected_attendance_date = st.date_input("Select day to mark attendance:", value=today_date, max_value=today_date, key="attendance_picker")

    st.caption("Defaults applied: **Mode:** Both (8:30 AM – 4:30 PM) | **Category:** SwipeReq | **Reason:** Daily Attendance")

    # Trigger button
    if st.button(f"👉 Swipe Attendance for {selected_attendance_date.strftime('%A, %d %b %Y')}", type="primary", use_container_width=True, key="attendance_swipe_btn"):
        if not emp_user or not emp_pass:
            st.error("Credentials missing. Please verify `SPINE_USER` and `SPINE_PASS` inside `.streamlit/secrets.toml` or Streamlit Cloud Secrets.")
        else:
            with st.spinner(f"Logging in and submitting attendance for {selected_attendance_date.strftime('%d-%b-%y')}..."):
                result = run_swipe_for_date(emp_user, emp_pass, selected_attendance_date)

            # Success / Error Handling (without screenshots)
            if result["status"] == "success":
                st.success(f"✅ Attendance successfully submitted for **{result['date']}** (Status: In Process)")
            else:
                st.error(f"Failed to submit attendance for {result['date']}: {result['message']}")
