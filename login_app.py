import streamlit as st
import sqlite3
import hashlib
from datetime import datetime
import os
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image
import chromadb
import pandas as pd
from chromadb.utils import embedding_functions

# Paths
LOGIN_DB_PATH = "database/admissions.db"
DATA_DB_PATH = "database/admissions.db"
VECTOR_DB_PATH = "vector_db"

# DB Setup
os.makedirs(os.path.dirname(LOGIN_DB_PATH), exist_ok=True)
os.makedirs(os.path.dirname(DATA_DB_PATH), exist_ok=True)
os.makedirs(VECTOR_DB_PATH, exist_ok=True)

chroma_client = chromadb.PersistentClient(path=VECTOR_DB_PATH)
collection = chroma_client.get_or_create_collection(
    name="student_documents",
    embedding_function=embedding_functions.DefaultEmbeddingFunction()
)

# ----------------- CACHED DB CONNECTION -----------------
@st.cache_resource
def get_db_connection():
    return sqlite3.connect(DATA_DB_PATH, check_same_thread=False)

# ----------------- LOGIN DB INIT -----------------
def init_login_db():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS Login_Credentials (
            Email TEXT PRIMARY KEY,
            Hashed_Password TEXT NOT NULL
        )
    """)
    conn.commit()

# ----------------- AUTH HELPERS -----------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_user(email, password):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT Hashed_Password FROM Login_Credentials WHERE Email=?", (email,))
    result = c.fetchone()
    if result:
        return result[0] == hash_password(password)
    return False

def add_user(email, password):
    conn = get_db_connection()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO Login_Credentials VALUES (?, ?)", (email, hash_password(password)))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def reset_password(email, new_pass):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM Login_Credentials WHERE Email=?", (email,))
    if c.fetchone():
        c.execute("UPDATE Login_Credentials SET Hashed_Password=? WHERE Email=?", (hash_password(new_pass), email))
        conn.commit()
        return True
    return False

# ----------------- OCR -----------------
def extract_text_from_scanned_pdf(uploaded_file):
    try:
        images = convert_from_bytes(uploaded_file.read())
        text = ""
        for img in images:
            text += pytesseract.image_to_string(img)
        return text
    except Exception as e:
        st.error(f"OCR failed: {str(e)}")
        return ""

# ----------------- DB OPERATIONS -----------------
def fetch_student_data(email):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT Name, Mobile_Number FROM Primary_Data WHERE Email=?", (email,))
    primary = cursor.fetchone()

    cursor.execute("""
        SELECT Aadhar_Number, DOB, Class_10_Year, Class_10_Avg_Marks, Class_12_Year,
               Class_12_Physics, Class_12_Maths, Class_12_Chemistry, JEE_Year,
               JEE_Rank, Stream_Applied
        FROM Application_Data WHERE Email=?
    """, (email,))
    app = cursor.fetchone()

    if primary and app:
        return {
            "Name": primary[0],
            "Mobile": primary[1],
            "Aadhar": app[0],
            "DOB": app[1],
            "Class10Year": app[2],
            "Class10Marks": app[3],
            "Class12Year": app[4],
            "Class12Physics": app[5],
            "Class12Maths": app[6],
            "Class12Chemistry": app[7],
            "JEEYear": app[8],
            "JEERank": app[9],
            "Stream": app[10],
        }
    return None

def upsert_student_data(email, name, mobile, aadhar, dob, class_10_year, class_10_marks,
                        class_12_year, class_12_physics, class_12_maths, class_12_chemistry,
                        jee_year, jee_rank, stream):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT Email FROM Primary_Data WHERE Email=?", (email,))
    exists = cursor.fetchone()

    try:
        if exists:
            cursor.execute("UPDATE Primary_Data SET Name=?, Mobile_Number=? WHERE Email=?",
                           (name, mobile, email))
            cursor.execute("""
                UPDATE Application_Data SET
                    Aadhar_Number=?, DOB=?, Class_10_Year=?, Class_10_Avg_Marks=?,
                    Class_12_Year=?, Class_12_Physics=?, Class_12_Maths=?, Class_12_Chemistry=?,
                    JEE_Year=?, JEE_Rank=?, Stream_Applied=?, last_validation=?
                WHERE Email=?
            """, (
                aadhar, dob, class_10_year, class_10_marks,
                class_12_year, class_12_physics, class_12_maths, class_12_chemistry,
                jee_year, jee_rank, stream, datetime.now(), email
            ))
        else:
            cursor.execute("INSERT INTO Primary_Data (Email, Name, Mobile_Number) VALUES (?, ?, ?)",
                           (email, name, mobile))
            cursor.execute("""
                INSERT INTO Application_Data (
                    Email, Aadhar_Number, DOB, Class_10_Year, Class_10_Avg_Marks,
                    Class_12_Year, Class_12_Physics, Class_12_Maths, Class_12_Chemistry,
                    JEE_Year, JEE_Rank, Stream_Applied, last_validation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                email, aadhar, dob, class_10_year, class_10_marks,
                class_12_year, class_12_physics, class_12_maths, class_12_chemistry,
                jee_year, jee_rank, stream, datetime.now()
            ))
            cursor.execute("INSERT INTO Admission_Results (Email) VALUES (?)", (email,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e

def update_documents(email, documents):
    doc_types = ["aadhar_card", "class_10_marksheet", "class_12_marksheet", "jee_rank_card"]
    for doc_type, doc_file in zip(doc_types, documents):
        if doc_file is not None:
            text = extract_text_from_scanned_pdf(doc_file)
            collection.upsert(
                documents=[text],
                metadatas=[{"email": email, "document_type": doc_type}],
                ids=[f"{email}_{doc_type}"]
            )
def fetch_admission_status(email):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT acceptance_status, acceptance_status_email_sent FROM Admission_Results WHERE Email=?", (email,))
    result = cursor.fetchone()

    if result:
        acceptance_status, email_sent = result
        if email_sent == 1:
            status = "Accepted"
        elif email_sent == 0 and acceptance_status == 0:
            status = "In Progress"
        else:
            status = "Rejected"
        return {"Email": email, "Status": status}
    return None
# ----------------- STREAMLIT APP -----------------
st.set_page_config(page_title="Student Admission Portal", layout="centered")
init_login_db()

if "page" not in st.session_state:
    st.session_state.page = "login"
#Show sidebar only after login
if st.session_state.page not in ["login", "signup"]:
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Select a page", ["Application Form", "Check Status"])

    if page == "Application Form":
        st.session_state.page = "form"
    elif page == "Check Status":
        st.session_state.page = "status"
    
# -------- LOGIN --------
if st.session_state.page == "login":
    st.title("Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        if verify_user(email, password):
            st.session_state.page = "form"
            st.session_state.email = email
            st.rerun()
        else:
            st.error("Invalid credentials")

    st.text("Don't have an account?")
    if st.button("Sign up"):
        st.session_state.page = "signup"
        st.rerun()

# -------- SIGNUP --------
elif st.session_state.page == "signup":
    st.title("Create Account")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    confirm = st.text_input("Confirm Password", type="password")
    if st.button("Register"):
        if password != confirm:
            st.error("Passwords do not match.")
        elif add_user(email, password):
            st.success("Account created. Please log in.")
            st.session_state.page = "login"
            st.rerun()
        else:
            st.error("Email already registered.")

    if st.button("Back to Login"):
        st.session_state.page = "login"
        st.rerun()

# ----------------- APPLICATION FORM -----------------
elif st.session_state.page == "form":
    st.title("Application Form")
    email = st.session_state.email
    existing_data = fetch_student_data(email)

    with st.form("student_form"):
        st.header("Personal Details")
        name = st.text_input("Full Name", value=existing_data["Name"] if existing_data else "")
        mobile = st.text_input("Mobile Number", value=existing_data["Mobile"] if existing_data else "")
        aadhar = st.text_input("Aadhar Number", value=existing_data["Aadhar"] if existing_data else "")
        dob = st.date_input("Date of Birth", value=datetime.strptime(existing_data["DOB"], "%Y-%m-%d").date() if existing_data else datetime.today().date())

        st.header("Academic Details")
        col1, col2 = st.columns(2)
        with col1:
            class_10_year = st.number_input("Class 10 Year", 2000, 2100, value=int(existing_data["Class10Year"]) if existing_data else 2020)
            class_10_marks = st.number_input("Class 10 Avg Marks (%)", 0.0, 100.0, value=float(existing_data["Class10Marks"]) if existing_data else 0.0)
        with col2:
            class_12_year = st.number_input("Class 12 Year", 2000, 2100, value=int(existing_data["Class12Year"]) if existing_data else 2022)
            class_12_physics = st.number_input("Class 12 Physics (%)", 0.0, 100.0, value=float(existing_data["Class12Physics"]) if existing_data else 0.0)
            class_12_maths = st.number_input("Class 12 Maths (%)", 0.0, 100.0, value=float(existing_data["Class12Maths"]) if existing_data else 0.0)
            class_12_chemistry = st.number_input("Class 12 Chemistry (%)", 0.0, 100.0, value=float(existing_data["Class12Chemistry"]) if existing_data else 0.0)

        st.header("JEE Details")
        jee_year = st.number_input("JEE Year", 2000, 2100, value=int(existing_data["JEEYear"]) if existing_data else 2024)
        jee_rank = st.number_input("JEE Rank", 0, value=int(existing_data["JEERank"]) if existing_data else 0)
        stream = st.selectbox("Stream Applied", ["CS", "ECE", "Mechanical", "Civil"], index=["CS", "ECE", "Mechanical", "Civil"].index(existing_data["Stream"]) if existing_data else 0)

        st.header("Upload/Replace Documents")
        aadhar_doc = st.file_uploader("Aadhar Card (PDF)", type="pdf")
        class_10_doc = st.file_uploader("Class 10 Marksheet", type="pdf")
        class_12_doc = st.file_uploader("Class 12 Marksheet", type="pdf")
        jee_rank_doc = st.file_uploader("JEE Rank Card", type="pdf")

        if st.form_submit_button("Submit / Update Application"):
            upsert_student_data(
                email, name, mobile, aadhar, dob, class_10_year, class_10_marks,
                class_12_year, class_12_physics, class_12_maths, class_12_chemistry,
                jee_year, jee_rank, stream
            )
            update_documents(email, [aadhar_doc, class_10_doc, class_12_doc, jee_rank_doc])
            st.success("Application submitted/updated successfully.")
# ----------- CHECK STATUS -------------
elif st.session_state.page == "status":
    st.title("Admission Status")
    email = st.session_state.email
    status = fetch_admission_status(email)

    if status:
        # Create a DataFrame to display the status in a table format
        df = pd.DataFrame([status])  # Wrap the status dictionary in a list to create a single row DataFrame
        
        # Display the DataFrame in a table
        st.dataframe(df)
    else:
        st.write("No admission status found.")
# ----------- LOGOUT -------------
elif st.session_state.page == "logout":
    st.session_state.email = None
    st.session_state.page = "login"
    st.success("Logged out successfully.")
    st.rerun()

# ----------------- LOGOUT BUTTON -----------------
if st.button("Logout"):
    st.session_state.page = "logout"
    st.rerun()
