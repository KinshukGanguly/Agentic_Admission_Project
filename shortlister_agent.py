import sqlite3
import json
from datetime import datetime
from typing import Type
import os
from crewai import Agent, Task, Crew
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


# ------------------ TOOL ------------------ #

class ShortlistInput(BaseModel):
    """Input schema for ShortlistingTool."""
    trigger: str = Field(..., description="triggering string to start the shortlisting process")


class ShortlistingTool(BaseTool):
    name: str = "Applicant Shortlisting Tool"
    description: str = "Shortlists candidates by JEE rank based on seat availability and logs results."
    args_schema: Type[BaseModel] = ShortlistInput

    def _run(self, trigger: str) -> str:
        conn = sqlite3.connect("database/admissions.db")
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")

        try:
            # Step 1: Fetch available seats
            cursor.execute("SELECT Stream, Available_Seats FROM Admission_Seats WHERE Available_Seats > 0")
            available_seats = dict(cursor.fetchall())

            # Step 2: Process applicants per stream
            for stream, seats in available_seats.items():
                cursor.execute("""
                    SELECT app.Email, app.JEE_Rank
                    FROM Application_Data AS app
                    LEFT JOIN Admission_Results AS res ON app.Email = res.Email
                    WHERE app.Stream_Applied = ?
                    AND (res.shortlisting_done IS NULL OR res.shortlisting_done = 0)
                    ORDER BY app.JEE_Rank ASC
                """, (stream,))
                applicants = cursor.fetchall()
                selected = 0

                for email, _ in applicants:
                    accepted = selected < seats

                    cursor.execute("""
                        INSERT OR REPLACE INTO Admission_Results (Email, shortlisting_done, acceptance_status, acceptance_status_email_sent)
                        VALUES (?, 1, ?, 0)
                    """, (email, int(accepted)))

                    if accepted:
                        cursor.execute("UPDATE Admission_Seats SET Available_Seats = Available_Seats - 1 WHERE Stream = ?", (stream,))
                        selected += 1

            # Step 3: Fetch students where shortlisting is done, but email not yet sent
            cursor.execute("""
                SELECT Email, acceptance_status
                FROM Admission_Results
                WHERE shortlisting_done = 1 AND acceptance_status_email_sent = 0
            """)
            shortlisted_students = cursor.fetchall()

            logs = []
            for email, status in shortlisted_students:
                logs.append({
                    "email": email,
                    "status": f"Application {'accepted' if status else 'rejected'}",
                    "issues": [""],
                    "timestamp": datetime.now().isoformat()
                })
            
            # Safely write to students.json
            students_file = "students.json"
            
            # Load existing logs if the file exists
            if os.path.exists(students_file):
                with open(students_file, "r") as f:
                    try:
                        existing_logs = json.load(f)
                    except json.JSONDecodeError:
                        print("⚠️ Warning: Malformed JSON in file. Starting fresh.")
                        existing_logs = []
            else:
                existing_logs = []
            
            # Extend and save back
            existing_logs.extend(logs)
            
            with open(students_file, "w") as f:
                json.dump(existing_logs, f, indent=4)
            
            print("✅ Logs updated in students.json")

            conn.commit()
            return "✅ Shortlisting completed and fresh shortlisted students logged to students.json."

        except Exception as e:
            return f"❌ Error during shortlisting: {str(e)}"

        finally:
            conn.close()


# ------------------ AGENT ------------------ #
ShortlisterAgent = Agent(
    role="Admissions Shortlister",
    goal="Shortlist applicants based on merit and seat availability",
    backstory="You are a highly efficient admissions officer who ensures a fair and transparent selection process.",
    tools=[ShortlistingTool()],
    memory=True,
    verbose=True,
)


# ------------------ TASK ------------------ #
ShortlistTask = Task(
    description="Execute the applicant shortlisting process by triggering the tool.",
    expected_output="Admission_Results table updated and email logs saved to students.json.",
    agent=ShortlisterAgent,
    output_file="shortlister_output.txt"
)


# ------------------ CREW ------------------ #
def run_shortlister_crew():
    crew = Crew(
        agents=[ShortlisterAgent],
        tasks=[ShortlistTask],
        verbose=True
    )
    result = crew.kickoff(inputs={"trigger": "start"})
    print("✅ Final Output:\n", result)


if __name__ == "__main__":
    run_shortlister_crew()
