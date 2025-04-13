'''import streamlit as st
import sqlite3
import hashlib
from datetime import datetime
import os
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image
import chromadb
from chromadb.utils import embedding_functions

# Paths
LOGIN_DB_PATH = "database/admissions.db"
DATA_DB_PATH = "database/admissions.db"
VECTOR_DB_PATH = "vector_db"

# DB Setup
os.makedirs(os.path.dirname(LOGIN_DB_PATH), exist_ok=True)
os.makedirs(os.path.dirname(DATA_DB_PATH), exist_ok=True)
os.makedirs(VECTOR_DB_PATH, exist_ok=True)

chroma_client = chromadb.PersistentClient(path="vector_db")
collection = chroma_client.get_or_create_collection(
    name="student_documents",
    embedding_function=embedding_functions.DefaultEmbeddingFunction()
)
# ----------------- LOGIN DB INIT -----------------
def init_login_db():
    conn = sqlite3.connect(LOGIN_DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS Login_Credentials (
            Email TEXT PRIMARY KEY,
            Hashed_Password TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# ----------------- AUTH HELPERS -----------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_user(email, password):
    conn = sqlite3.connect(LOGIN_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT Hashed_Password FROM Login_Credentials WHERE Email=?", (email,))
    result = c.fetchone()
    conn.close()
    if result:
        return result[0] == hash_password(password)
    return False

def add_user(email, password):
    conn = sqlite3.connect(LOGIN_DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO Login_Credentials VALUES (?, ?)", (email, hash_password(password)))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def change_password(email, old_pass, new_pass):
    if verify_user(email, old_pass):
        conn = sqlite3.connect(LOGIN_DB_PATH)
        c = conn.cursor()
        c.execute("UPDATE Login_Credentials SET Hashed_Password=? WHERE Email=?", (hash_password(new_pass), email))
        conn.commit()
        conn.close()
        return True
    return False

def reset_password(email, new_pass):
    conn = sqlite3.connect(LOGIN_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM Login_Credentials WHERE Email=?", (email,))
    if c.fetchone():
        c.execute("UPDATE Login_Credentials SET Hashed_Password=? WHERE Email=?", (hash_password(new_pass), email))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

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

#def generate_regn_id():
#    conn = sqlite3.connect(DATA_DB_PATH)
#    cursor = conn.cursor()
#    cursor.execute("SELECT Regn_ID FROM Primary_Data ORDER BY Regn_ID")
#    existing_ids = [row[0] for row in cursor.fetchall()]
#    for i in range(0, 1000):
#        candidate_id = f"ST_2025_{i:03d}"
#        if candidate_id not in existing_ids:
#            return candidate_id
#    raise Exception("No available Regn_ID slots!")
import sqlite3
from datetime import datetime

def register_student(name, email, mobile, aadhar, dob, class_10_year, class_10_marks,
                     class_12_year, class_12_physics, class_12_maths, class_12_chemistry,
                     jee_year, jee_rank, stream, documents):

    conn = sqlite3.connect(DATA_DB_PATH)
    cursor = conn.cursor()

    try:
        # Insert into Primary_Data
        cursor.execute("""
            INSERT INTO Primary_Data (Email, Name, Mobile_Number)
            VALUES (?, ?, ?)
        """, (email, name, mobile))

        # Insert into Application_Data
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

        cursor.execute("""
            INSERT INTO Admission_result (Email) VALUES (email)""", (email))

        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise ValueError(f"Database integrity error: {e}")
    finally:
        conn.close()

    # Store documents using the Email as ID reference
    doc_types = ["aadhar_card", "class_10_marksheet", "class_12_marksheet", "jee_rank_card"]
    for doc_type, doc_file in zip(doc_types, documents):
        if doc_file is not None:
            text = extract_text_from_scanned_pdf(doc_file)
            collection.add(
                documents=[text],
                metadatas=[{"email": email, "document_type": doc_type}],
                ids=[f"{email}_{doc_type}"]
            )

    return email


# ----------------- APP START -----------------

st.set_page_config(page_title="Admission Portal", layout="wide")

if "page" not in st.session_state:
    st.session_state.page = "login"

# ----------------- LOGIN PAGE -----------------
if st.session_state.page == "login":
    st.title("🔐 Login to Admission Portal")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        if verify_user(email, password):
            st.session_state.page = "form"
            st.session_state.email = email
            st.rerun()
        else:
            st.error("Invalid credentials")

    st.markdown("👉 Forgot password?")
    if st.button("Reset Password"):
        st.session_state.page = "forgot"

    st.markdown("👉 Don't have an account?")
    if st.button("Sign up"):
        st.session_state.page = "signup"

# ----------------- SIGNUP PAGE -----------------
elif st.session_state.page == "signup":
    st.title("📝 Sign Up")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    confirm = st.text_input("Confirm Password", type="password")

    if st.button("Create Account"):
        if password != confirm:
            st.error("Passwords do not match")
        elif add_user(email, password):
            st.success("Account created. Please log in.")
            st.session_state.page = "login"
            st.rerun()
        else:
            st.error("Email already exists")

    if st.button("Back to Login"):
        st.session_state.page = "login"
        st.rerun()

# ----------------- FORGOT PASSWORD -----------------
elif st.session_state.page == "forgot":
    st.title("🔁 Forgot Password")
    email = st.text_input("Registered Email")
    new_pass = st.text_input("New Password", type="password")

    if st.button("Reset Password"):
        if reset_password(email, new_pass):
            st.success("Password updated successfully")
            st.session_state.page = "login"
            st.rerun()
        else:
            st.error("Email not found")

    if st.button("Back"):
        st.session_state.page = "login"
        st.rerun()

# ----------------- APPLICATION FORM -----------------
elif st.session_state.page == "form":
    st.title("🎓 Student Application Form (OCR Enabled)")
    with st.form("student_form"):
        st.header("Personal Details")
        name = st.text_input("Full Name")
        email = st.session_state.email  # from login
        mobile = st.text_input("Mobile Number")
        aadhar = st.text_input("Aadhar Number")
        dob = st.date_input("Date of Birth")

        st.header("Academic Details")
        col1, col2 = st.columns(2)
        with col1:
            class_10_year = st.number_input("Class 10 Year", 2000, 2100)
            class_10_marks = st.number_input("Class 10 Avg Marks (%)", 0.0, 100.0)
        with col2:
            class_12_year = st.number_input("Class 12 Year", 2000, 2100)
            class_12_physics = st.number_input("Class 12 Physics (%)", 0.0, 100.0)
            class_12_maths = st.number_input("Class 12 Maths (%)", 0.0, 100.0)
            class_12_chemistry = st.number_input("Class 12 Chemistry (%)", 0.0, 100.0)

        st.header("JEE Details")
        jee_year = st.number_input("JEE Year", 2000, 2100)
        jee_rank = st.number_input("JEE Rank", 0)
        stream = st.selectbox("Stream Applied", ["CS", "ECE", "Mechanical", "Civil"])

        st.header("Upload Documents")
        aadhar_doc = st.file_uploader("Aadhar Card (PDF)", type="pdf")
        class_10_doc = st.file_uploader("Class 10 Marksheet", type="pdf")
        class_12_doc = st.file_uploader("Class 12 Marksheet", type="pdf")
        jee_rank_doc = st.file_uploader("JEE Rank Card", type="pdf")

        if st.form_submit_button("Submit Application"):
            docs = [aadhar_doc, class_10_doc, class_12_doc, jee_rank_doc]
            if None in docs:
                st.error("Upload all documents.")
            else:
                regn_id = register_student(
                    name, email, mobile, aadhar, dob, class_10_year, class_10_marks,
                    class_12_year, class_12_physics, class_12_maths, class_12_chemistry,
                    jee_year, jee_rank, stream, docs
                )
                st.success(f"Application submitted! Regn_ID: {regn_id}")'''

import streamlit as st
import sqlite3
import hashlib
from datetime import datetime
import os
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image
import chromadb
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

# ----------------- LOGIN DB INIT -----------------
def init_login_db():
    conn = sqlite3.connect(LOGIN_DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS Login_Credentials (
            Email TEXT PRIMARY KEY,
            Hashed_Password TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

# ----------------- AUTH HELPERS -----------------
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_user(email, password):
    conn = sqlite3.connect(LOGIN_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT Hashed_Password FROM Login_Credentials WHERE Email=?", (email,))
    result = c.fetchone()
    conn.close()
    if result:
        return result[0] == hash_password(password)
    return False

def add_user(email, password):
    conn = sqlite3.connect(LOGIN_DB_PATH)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO Login_Credentials VALUES (?, ?)", (email, hash_password(password)))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def reset_password(email, new_pass):
    conn = sqlite3.connect(LOGIN_DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM Login_Credentials WHERE Email=?", (email,))
    if c.fetchone():
        c.execute("UPDATE Login_Credentials SET Hashed_Password=? WHERE Email=?", (hash_password(new_pass), email))
        conn.commit()
        conn.close()
        return True
    conn.close()
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
    conn = sqlite3.connect(DATA_DB_PATH)
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
    conn.close()

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
    conn = sqlite3.connect(DATA_DB_PATH)
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
            cursor.execute("INSERT INTO Admission_result (Email) VALUES (?)", (email,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

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

# ----------------- STREAMLIT APP -----------------
st.set_page_config(page_title="Admission Portal", layout="wide")
init_login_db()

if "page" not in st.session_state:
    st.session_state.page = "login"

# ----------------- LOGIN -----------------
if st.session_state.page == "login":
    st.title("🔐 Login to Admission Portal")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        if verify_user(email, password):
            st.session_state.page = "form"
            st.session_state.email = email
            st.rerun()
        else:
            st.error("Invalid credentials")

    st.markdown("👉 Forgot password?")
    if st.button("Reset Password"):
        st.session_state.page = "forgot"

    st.markdown("👉 Don't have an account?")
    if st.button("Sign up"):
        st.session_state.page = "signup"

# ----------------- SIGN UP -----------------
elif st.session_state.page == "signup":
    st.title("📝 Sign Up")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    confirm = st.text_input("Confirm Password", type="password")

    if st.button("Create Account"):
        if password != confirm:
            st.error("Passwords do not match")
        elif add_user(email, password):
            st.success("Account created. Please log in.")
            st.session_state.page = "login"
            st.rerun()
        else:
            st.error("Email already exists")

    if st.button("Back to Login"):
        st.session_state.page = "login"
        st.rerun()

# ----------------- FORGOT PASSWORD -----------------
elif st.session_state.page == "forgot":
    st.title("🔁 Forgot Password")
    email = st.text_input("Registered Email")
    new_pass = st.text_input("New Password", type="password")

    if st.button("Reset Password"):
        if reset_password(email, new_pass):
            st.success("Password updated successfully")
            st.session_state.page = "login"
            st.rerun()
        else:
            st.error("Email not found")

    if st.button("Back"):
        st.session_state.page = "login"
        st.rerun()

# ----------------- APPLICATION FORM -----------------
elif st.session_state.page == "form":
    st.title("🎓 Student Application Form (OCR Enabled)")
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

#-----------LOGOUT-------------
elif st.session_state.page == "logout":
    st.session_state.email = None
    st.session_state.page = "login"
    st.success("Logged out successfully.")
    st.rerun()
# ----------------- LOGOUT -----------------
if st.button("Logout"):
    st.session_state.page = "logout"
    st.rerun()
# ----------------- END OF APP -----------------
# ----------------- END OF APP -----------------