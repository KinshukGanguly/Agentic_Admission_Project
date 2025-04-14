import sqlite3
import json
from datetime import datetime
from typing import Type

from crewai import Agent, Task, Crew
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


# ------------------ TOOL ------------------ #
class ShortlistInput(BaseModel):
    """Input schema for ShortlistingTool."""
    trigger: str = Field(..., description="Just pass any string to trigger shortlisting")


class ShortlistingTool(BaseTool):
    name: str = "Applicant Shortlisting Tool"
    description: str = "Shortlists candidates by JEE rank based on seat availability and logs results."
    args_schema: Type[BaseModel] = ShortlistInput

    def _run(self, trigger: str) -> str:
        conn = sqlite3.connect("database/admissions.db")
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")

        try:
            cursor.execute("SELECT Stream, Available_Seats FROM Admission_Seats WHERE Available_Seats > 0")
            available_seats = dict(cursor.fetchall())

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

                    cursor.execute("UPDATE Admission_Results SET shortlisting_done = 1 WHERE Email = ?", (email,))

                    if accepted:
                        cursor.execute("UPDATE Admission_Seats SET Available_Seats = Available_Seats - 1 WHERE Stream = ?", (stream,))
                        self._log_email(email, "accepted")
                        selected += 1
                    else:
                        self._log_email(email, "rejected")

            conn.commit()
            return "✅ Shortlisting completed and results updated."

        except Exception as e:
            return f"❌ Error during shortlisting: {str(e)}"

        finally:
            conn.close()

    def _log_email(self, email, status):
        log_path = "students.json"
        log_entry = {
            "email": email,
            "status": f"Application {status}",
            "issues": [""],
            "timestamp": datetime.now().isoformat()
        }

        try:
            with open(log_path, "r") as f:
                logs = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logs = []

        logs.append(log_entry)
        with open(log_path, "w") as f:
            json.dump(logs, f, indent=4)


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
    expected_output="Admission_Results table updated and email logs saved to email_log.json.",
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
