import streamlit as st
import sqlite3
import chromadb
from chromadb.utils import embedding_functions
import os
import pytesseract
from pdf2image import convert_from_bytes
from PIL import Image
import io

# make folder by my choice if they don't exist already
os.makedirs("database", exist_ok=True)
os.makedirs("vector_db", exist_ok=True)


chroma_client = chromadb.PersistentClient(path="vector_db")
collection = chroma_client.get_or_create_collection(
    name="student_documents",
    embedding_function=embedding_functions.DefaultEmbeddingFunction()
)

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

def generate_regn_id():
    conn = sqlite3.connect("database/admissions.db")
    cursor = conn.cursor()
    cursor.execute("SELECT Regn_ID FROM Primary_Data ORDER BY Regn_ID")
    existing_ids = [row[0] for row in cursor.fetchall()]
    for i in range(0, 1000):
        candidate_id = f"ST_2025_{i:03d}"
        if candidate_id not in existing_ids:
            return candidate_id
    raise Exception("No available Regn_ID slots!")


def register_student(name, email, mobile, aadhar, dob, class_10_year, class_10_marks,
                    class_12_year, class_12_physics, class_12_maths, class_12_chemistry,
                    jee_year, jee_rank, stream, documents):
    regn_id = generate_regn_id()
    

    conn = sqlite3.connect("database/admissions.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO Primary_Data (Regn_ID, Name, Email, Mobile_Number) VALUES (?, ?, ?, ?)",
                   (regn_id, name, email, mobile))
    cursor.execute("""
        INSERT INTO Application_Data (
        Regn_ID, Aadhar_Number, DOB, Class_10_Year, Class_10_Avg_Marks, Class_12_Year, Class_12_Physics, Class_12_Maths, Class_12_Chemistry,JEE_Year, JEE_Rank, Stream_Applied
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (regn_id, aadhar, dob, class_10_year, class_10_marks, class_12_year, class_12_physics, class_12_maths, class_12_chemistry,jee_year, jee_rank, stream
    ))
    conn.commit()
    conn.close()

    doc_types = ["aadhar_card", "class_10_marksheet", "class_12_marksheet", "jee_rank_card"]
    for doc_type, doc_file in zip(doc_types, documents):
        if doc_file is not None:
            text = extract_text_from_scanned_pdf(doc_file)
            collection.add(
                documents=[text],
                metadatas=[{"regn_id": regn_id, "document_type": doc_type}],
                ids=[f"{regn_id}_{doc_type}"]
            )
    return regn_id

# Streamlit 
st.title("🎓 Student Application Form (OCR Enabled)")
with st.form("student_form"):
    st.header("Personal Details")
    name = st.text_input("Full Name", key="name")
    email = st.text_input("Email", key="email")
    mobile = st.text_input("Mobile Number", key="mobile")
    aadhar = st.text_input("Aadhar Number", key="aadhar")
    dob = st.date_input("Date of Birth", key="dob")

    st.header("Academic Details")
    col1, col2 = st.columns(2)
    with col1:
        class_10_year = st.number_input("Class 10 Year", min_value=2000, max_value=2100, key="class_10_year")
        class_10_marks = st.number_input("Class 10 Avg Marks (%)", min_value=0.0, max_value=100.0, key="class_10_marks")
    with col2:
        class_12_year = st.number_input("Class 12 Year", min_value=2000, max_value=2100, key="class_12_year")
        class_12_physics = st.number_input("Class 12 Physics (%)", min_value=0.0, max_value=100.0, key="class_12_physics")
        class_12_maths = st.number_input("Class 12 Maths (%)", min_value=0.0, max_value=100.0, key="class_12_maths")
        class_12_chemistry = st.number_input("Class 12 Chemistry (%)", min_value=0.0, max_value=100.0, key="class_12_chemistry")

    st.header("JEE Details")
    jee_year = st.number_input("JEE Year", min_value=2000, max_value=2100, key="jee_year")
    jee_rank = st.number_input("JEE Rank", min_value=0, key="jee_rank")
    stream = st.selectbox("Stream Applied", ["CS", "ECE", "Mechanical", "Civil"], key="stream")

    st.header("Upload Documents (PDFs only)")
    aadhar_doc = st.file_uploader("Aadhar Card", type="pdf", key="aadhar_doc")
    class_10_doc = st.file_uploader("Class 10 Marksheet", type="pdf", key="class_10_doc")
    class_12_doc = st.file_uploader("Class 12 Marksheet", type="pdf", key="class_12_doc")
    jee_rank_doc = st.file_uploader("JEE Rank Card", type="pdf", key="jee_rank_doc")

    submitted = st.form_submit_button("Submit Application")
    
    if submitted:
        documents = [
            st.session_state.aadhar_doc,
            st.session_state.class_10_doc,
            st.session_state.class_12_doc,
            st.session_state.jee_rank_doc
        ]
        
        if None in documents:
            st.error("Please upload all 4 documents!")
        else:
            regn_id = register_student(
                st.session_state.name,
                st.session_state.email,
                st.session_state.mobile,
                st.session_state.aadhar,
                st.session_state.dob,
                st.session_state.class_10_year,
                st.session_state.class_10_marks,
                st.session_state.class_12_year,
                st.session_state.class_12_physics,
                st.session_state.class_12_maths,
                st.session_state.class_12_chemistry,
                st.session_state.jee_year,
                st.session_state.jee_rank,
                st.session_state.stream,
                documents
            )
            st.success(f"Application submitted! Your Regn_ID: {regn_id}")