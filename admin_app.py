import streamlit as st
import sqlite3
import hashlib
import pandas as pd
from datetime import datetime
import os

# Import the chatbot function
from chatbot import ask_admin_bot

DB_PATH = "database/admissions.db"

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def init_admin():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS Login_Credentials (
            Email TEXT PRIMARY KEY,
            Hashed_Password TEXT NOT NULL
        )
    """)
    c.execute("""
        INSERT OR IGNORE INTO Login_Credentials (Email, Hashed_Password)
        VALUES (?, ?)
    """, ("admin@gmail.com", hash_password("admin@123")))
    conn.commit()
    conn.close()

def verify_admin(email, password):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT Hashed_Password FROM Login_Credentials WHERE Email=?", (email,))
    result = c.fetchone()
    conn.close()
    if result:
        return result[0] == hash_password(password)
    return False

def get_admission_seats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM Admission_Seats")
    rows = c.fetchall()
    conn.close()
    return rows

def upsert_admission_seat(stream, total, available):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        INSERT INTO Admission_Seats (Stream, Total_Seats, Available_Seats)
        VALUES (?, ?, ?)
        ON CONFLICT(Stream) DO UPDATE SET Total_Seats=excluded.Total_Seats, Available_Seats=excluded.Available_Seats
    """, (stream, total, available))
    conn.commit()
    conn.close()
def get_application_data():
    conn = sqlite3.connect("database/admissions.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT 
            Email,
            Aadhar_Number,
            DOB,
            Class_10_Year,
            Class_10_Avg_Marks,
            Class_12_Year,
            Class_12_Physics,
            Class_12_Maths,
            Class_12_Chemistry,
            JEE_Year,
            JEE_Rank,
            Stream_Applied,
            application_validation_done,
            application_valid,
            error_observed,
            application_validation_status_email_sent,
            application_edited,
            validation_attempts,
            last_validation
        FROM Application_Data
    """)
    
    results = cursor.fetchall()
    conn.close()
    return results


# --- Initialize Admin User ---
init_admin()

# --- Streamlit UI Configuration ---
st.set_page_config(
    page_title="Admissions Admin Portal",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Session State Initialization ---
if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False
if "admin_email" not in st.session_state:
    st.session_state.admin_email = ""
if "chat_messages" not in st.session_state:
    st.session_state.chat_messages = []

# --- Admin Login Section ---
if not st.session_state.admin_logged_in:
    st.markdown("<h1 style='text-align: center;'>Admission Cell Portal</h1>", unsafe_allow_html=True)
    st.markdown("---")
    col1, col_main, col3 = st.columns([1, 2, 1])

    with col_main:
        with st.container():
            st.subheader("🔐 Admin Login")
            email = st.text_input("Email", key="login_email", placeholder="admin@example.com")
            password = st.text_input("Password", type="password", key="login_password", placeholder="password")

            login_button = st.button("Login", type="primary", use_container_width=True)

            if login_button:
                if verify_admin(email, password):
                    st.session_state.admin_logged_in = True
                    st.session_state.admin_email = email
                    st.success("Logged in successfully!")
                    st.rerun()
                else:
                    st.error("Invalid email or password. Please try again.")

# --- Admin Dashboard Section ---
else:
    # --- Sidebar Navigation ---
    with st.sidebar:
        st.title("👨‍💻 Admin Panel")
        st.write(f"Welcome, {st.session_state.admin_email}")
        st.divider()

        menu_options = {
            "🔵 Manage Seats": "Seats",
            "📈 View Results": "Results",
            "🤖 Ask Assistant": "Assistant"
        }
        selected_page = st.selectbox("Navigation", options=list(menu_options.keys()))
        page_key = menu_options[selected_page]

        st.divider()
        if st.button("Logout", use_container_width=True):
            st.session_state.admin_logged_in = False
            st.session_state.admin_email = ""
            st.session_state.chat_messages = []  # Optional: clear chat on logout
            st.success("You have been logged out.")
            st.rerun()

    # --- Main Content Area ---
    st.title(f"📊 Admin Dashboard")
    st.divider()

    # --- Page: Manage Admission Seats ---
    if page_key == "Seats":
        st.header("🔵Manage Admission Seats")

        col_form, col_table = st.columns([1, 2])

        with col_form:
            st.subheader("✏️ Add / Update Seat Allocation")
            current_seats_df = pd.DataFrame(get_admission_seats(), columns=["Stream", "Total_Seats", "Available_Seats"])

            streams = ["CS", "ECE", "Mechanical", "Civil"] + [s for s in current_seats_df['Stream'].unique() if s not in ["CS", "ECE", "Mechanical", "Civil"]]
            stream_options = sorted(list(set(streams)))

            with st.form("seat_form"):
                selected_stream = st.selectbox("Select Stream", options=stream_options)

                default_total, default_available = 0, 0
                if not current_seats_df.empty and selected_stream in current_seats_df['Stream'].values:
                    try:
                        existing_data = current_seats_df[current_seats_df['Stream'] == selected_stream].iloc[0]
                        default_total = int(existing_data['Total_Seats'])
                        default_available = int(existing_data['Available_Seats'])
                    except (KeyError, IndexError):
                        st.warning(f"Could not retrieve existing data for stream {selected_stream}")

                total_seats = st.number_input("Total Seats", min_value=0, value=default_total, step=1)
                available_seats = st.number_input("Available Seats", min_value=0, max_value=total_seats, value=min(default_available, total_seats), step=1)

                submitted = st.form_submit_button("Save Changes")
                if submitted:
                    if available_seats > total_seats:
                        st.warning("Available seats cannot exceed total seats.")
                    else:
                        upsert_admission_seat(selected_stream, total_seats, available_seats)
                        st.rerun()

        with col_table:
            st.subheader("Current Seat Allocation")
            seat_data_display = pd.DataFrame(get_admission_seats(), columns=["Stream", "Total_Seats", "Available_Seats"])

            if not seat_data_display.empty:
                st.dataframe(seat_data_display, use_container_width=True)
            else:
                st.write("No seat data to display.")

            if st.button("🔄 Refresh Table"):
                st.rerun()

    # --- Page: Admission Results ---
    elif page_key == "Results":
        st.header("📈 View Admission Results")

        df_results = pd.DataFrame(get_application_data(), columns=[
            "Email",
            "Aadhar_Number",
            "DOB",
            "Class_10_Year",
            "Class_10_Avg_Marks",
            "Class_12_Year",
            "Class_12_Physics",
            "Class_12_Maths",
            "Class_12_Chemistry",
            "JEE_Year",
            "JEE_Rank",
            "Stream_Applied",
            "application_validation_done",
            "application_valid",
            "error_observed",
            "application_validation_status_email_sent",
            "application_edited",
            "validation_attempts",
            "last_validation"
        ])
        if not df_results.empty:
            csv = df_results.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Results as CSV",
                data=csv,
                file_name='admission_results.csv',
                mime='text/csv',
            )
            st.dataframe(df_results, use_container_width=True)
        else:
            st.info("No admission results found.")

    # --- Page: Ask Assistant ---
    elif page_key == "Assistant":
        st.header("🤖 Ask Admissions Assistant")
        st.info("Query the admissions database using natural language.")

        for msg in st.session_state.chat_messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        user_input = st.chat_input("Ask the assistant about admissions data...")
        if user_input:
            st.session_state.chat_messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)

            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                with st.spinner("⚙️ Thinking..."):
                    try:
                        response = ask_admin_bot(user_input)
                        assistant_response = response.get("output", "Sorry, no response.")
                        message_placeholder.markdown(assistant_response)
                        st.session_state.chat_messages.append({"role": "assistant", "content": assistant_response})
                    except Exception as e:
                        st.error(f"Error: {e}")
                        assistant_response = "Sorry, something went wrong."
                        message_placeholder.markdown(assistant_response)

        st.divider()
        if st.button("🗑️ Clear Conversation"):
            st.session_state.chat_messages = []
            st.rerun()
