# admin_app.py
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

def get_admission_results():
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM Admission_Results", conn)
    conn.close()
    return df

# Initialize admin
init_admin()

st.set_page_config(page_title="Admin Dashboard", layout="wide")

if "admin_logged_in" not in st.session_state:
    st.session_state.admin_logged_in = False

# ---------------- LOGIN -----------------
if not st.session_state.admin_logged_in:
    st.title("🔐 Admin Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        if verify_admin(email, password):
            st.session_state.admin_logged_in = True
            st.success("Logged in successfully!")
            st.rerun()
        else:
            st.error("Invalid credentials")

else:
    st.title("📊 Admin Dashboard")
    st.sidebar.success("Logged in as admin@gmail.com")

    menu = st.sidebar.radio("Navigate", ["Admission Seats", "Admission Results", "Ask Assistant", "Logout"])

    if menu == "Admission Seats":
        st.header("🎯 Manage Admission Seats")

        rows = get_admission_seats()
        seat_data = {row[0]: row for row in rows}

        with st.form("seat_form"):
            stream = st.selectbox("Stream", ["CS", "ECE", "Mechanical", "Civil"])
            existing = seat_data.get(stream, (stream, 0, 0))
            total = st.number_input("Total Seats", min_value=0, value=existing[1])
            available = st.number_input("Available Seats", min_value=0, value=existing[2])
            submitted = st.form_submit_button("Save")
            if submitted:
                upsert_admission_seat(stream, total, available)
                st.success("Seats updated!")
                st.rerun()

        st.subheader("📋 Current Seat Data")
        st.table(get_admission_seats())

    elif menu == "Admission Results":
        st.header("📄 Admission Results")
        df = get_admission_results()
        st.dataframe(df, use_container_width=True)

    elif menu == "Ask Assistant":
        st.header("💡 Ask Admissions Assistant")

        if "messages" not in st.session_state:
            st.session_state.messages = []

        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        user_input = st.chat_input("Ask about admissions, applications, results...")
        if user_input:
            st.session_state.messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)
            with st.chat_message("assistant"):
                message_placeholder = st.empty()
                with st.spinner("Thinking..."):
                    response = ask_admin_bot(user_input)
                    if isinstance(response, dict) and 'output' in response:
                        message_placeholder.markdown(response['output'])
                        st.session_state.messages.append({"role": "assistant", "content": response['output']})
                    else:
                        message_placeholder.markdown(response)
                        st.session_state.messages.append({"role": "assistant", "content": response})


        if st.button("Clear Conversation"):
            st.session_state.messages = []
            st.rerun()

    elif menu == "Logout":
        st.session_state.admin_logged_in = False
        st.success("Logged out successfully.")
        st.rerun()