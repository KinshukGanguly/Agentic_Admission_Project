import os
import json
import sqlite3
from datetime import datetime
from crewai import Agent, Crew, Task
from crewai_tools import VectorDBTool
from crewai.tools import VectorDBTool, BaseTool
from pydantic import BaseModel
from typing import Type
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get OpenAI API key
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

# Connect to your SQLite database
conn = sqlite3.connect("admissions.db")
cursor = conn.cursor()

# Define the document verification tool
class DocumentVerificationTool(BaseTool):
    name: str = "DocumentVerificationTool"
    description: str = "Validates student application fields against unstructured document text from vector DB."

    class ToolInput(BaseModel):
        email: str
        student_name: str
        application_data: dict

    def _run(self, email: str, student_name: str, application_data: dict) -> dict:
        vector_tool = VectorDBTool.from_local(directory="./vector_db", name="student-docs")

        query = (
            f"Extract relevant fields like student name, aadhar number, JEE roll number, DOB, JEE rank for {email}"
        )
        doc_chunks = vector_tool.run(query)
        doc_text = "\n".join(doc_chunks).lower()

        issues = []
        status = "application_validation_passed"

        # Check for presence and match
        if student_name.lower() not in doc_text:
            issues.append("Student name in document does not match the entered name.")

        if application_data.get("aadhar_number", "").lower() not in doc_text:
            issues.append("Entered aadhar number doesn't match with document.")

        if application_data.get("jee_rank", "").lower() not in doc_text:
            issues.append("Entered JEE Rank doesn't match with document.")

        if issues:
            status = "application_validation_failed"

        return {
            "email": email,
            "status": status,
            "issues": issues,
            "timestamp": datetime.now().isoformat()
        }

# Define the validation agent
validator_agent = Agent(
    role="Document Validator",
    goal="Ensure student application fields are correctly validated against unstructured document text using vector DB.",
    backstory=(
        "You are responsible for verifying whether the details entered by a student in the application database "
        "match the actual information extracted from uploaded documents (stored in a vector DB). "
        "Ensure the name is correct and that no one uploads documents of someone else. "
        "Compare fields like Aadhar number, JEE Rank, etc. If valid, set application_valid to true. "
        "If mismatches occur, report detailed issues in the output and set application_valid to false."
    ),
    tools=[DocumentVerificationTool()],
    verbose=True,
    memory=True
)

def validate_all_applications():
    cursor.execute("""
        SELECT Email, Student_Name, Aadhar_Number, JEE_Rank FROM Application_Data
        WHERE application_validation_done = 0 OR application_edited = 1
    """)
    applications = cursor.fetchall()

    results = []
    for app in applications:
        email, student_name, aadhar_number, jee_rank = app

        application_data = {
            "aadhar_number": str(aadhar_number),
            "jee_rank": str(jee_rank)
        }

        # Run the validation task via Crew
        task = Task(
            description="Validate documents against application fields for email: {}".format(email),
            expected_output="Validation result with status, issues, timestamp",
            agent=validator_agent,
            inputs={
                "email": email,
                "student_name": student_name,
                "application_data": application_data
            }
        )

        crew = Crew(
            agents=[validator_agent],
            tasks=[task],
            verbose=True
        )

        result = crew.kickoff()

        # Extract fields from result for db + JSON
        status = result['status']
        issues = result['issues']

        # Update validation flags
        cursor.execute("""
            UPDATE Application_Data
            SET application_validation_done = 1,
                application_valid = ?,
                application_edited = 0
            WHERE Email = ?
        """, (1 if status == "application_validation_passed" else 0, email))
        conn.commit()

        # Write result to JSON
        results.append({
            "email": email,
            "status": status,
            "issues": issues,
            "timestamp": result["timestamp"]
        })

    with open("validation_results.json", "w") as f:
        json.dump(results, f, indent=4)

if __name__ == "__main__":
    validate_all_applications()
    print("Document validation completed.")
