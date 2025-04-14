import sqlite3
import json
from datetime import datetime
from typing import Type
from crewai import Agent, Task, Crew
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

# ------------------ TOOL ------------------ #
class ValidationInput(BaseModel):
    """Input schema for DocumentValidatorTool."""
    trigger: str = Field(..., description="Any string to trigger validation")

class DocumentValidatorTool(BaseTool):
    name: str = "Document Validation Tool"
    description: str = "Validates application data against admission criteria and logs results."
    args_schema: Type[BaseModel] = ValidationInput

    def _run(self, trigger: str) -> str:
        current_year = datetime.now().year
        validation_results = []
        
        conn = sqlite3.connect("database/admissions.db")
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys = ON")
        
        try:
            # Get applications needing validation
            cursor.execute("""
                SELECT p.Email, p.Mobile_Number, 
                       a.Aadhar_Number, a.DOB,
                       a.Class_10_Year, a.Class_10_Avg_Marks,
                       a.Class_12_Year, a.Class_12_Physics, 
                       a.Class_12_Maths, a.Class_12_Chemistry,
                       a.JEE_Year, a.application_edited
                FROM Application_Data a
                JOIN Primary_Data p ON a.Email = p.Email
                WHERE a.application_validation_done = 0 
                   OR (a.application_validation_done = 1 AND a.application_edited = 1)
            """)
            
            applications = cursor.fetchall()
            
            for app in applications:
                issues = []
                email = app[0]
                
                # Validate mobile number (exactly 10 digits)
                if not (app[1].isdigit() and len(app[1]) == 10):
                    issues.append("Invalid mobile number (must be 10 digits)")
                
                # Validate Aadhar (exactly 12 digits)
                if not (app[2].isdigit() and len(app[2]) == 12):
                    issues.append("Invalid Aadhar number (must be 12 digits)")
                
                # Validate Class 10 year (not older than 4 years)
                if (current_year - app[4]) > 4:
                    issues.append(f"Class 10 year {app[4]} is more than 4 years old")
                
                # Validate Class 12 year (not older than 2 years)
                if (current_year - app[6]) > 2:
                    issues.append(f"Class 12 year {app[6]} is more than 2 years old")
                
                # Validate JEE year (current year)
                if app[9] != current_year:
                    issues.append(f"JEE year {app[9]} must be current year {current_year}")
                
                # Validate marks ranges
                marks_checks = [
                    (app[5], "Class 10 Average Marks", 0, 100),
                    (app[7], "Class 12 Physics", 75, 100),
                    (app[8], "Class 12 Maths", 75, 100),
                    (app[9], "Class 12 Chemistry", 75, 100)
                ]
                
                for mark, subject, min_score, max_score in marks_checks:
                    if not (min_score <= mark <= max_score):
                        issues.append(f"{subject} {mark}% out of range ({min_score}-{max_score}%)")
                
                # Update validation status
                cursor.execute("""
                    UPDATE Application_Data 
                    SET application_validation_done = 1,
                        application_valid = ?,
                        error_observed = ?,
                        validation_attempts = validation_attempts + 1,
                        last_validation = CURRENT_TIMESTAMP,
                        application_edited = 0
                    WHERE Email = ?
                """, (len(issues) == 0, json.dumps(issues), email))
                
                # Log results
                validation_results.append({
                    "email": email,
                    "status": "valid" if len(issues) == 0 else "invalid",
                    "issues": issues,
                    "timestamp": datetime.now().isoformat()
                })
            
            conn.commit()
            self._save_results(validation_results)
            return f"✅ Validated {len(applications)} applications. Results saved to student.json"
            
        except Exception as e:
            conn.rollback()
            return f"❌ Validation error: {str(e)}"
        finally:
            conn.close()

    def _save_results(self, results):
        try:
            with open("student.json", "w") as f:
                json.dump(results, f, indent=4)
        except Exception as e:
            print(f"Error saving results: {str(e)}")

# ------------------ AGENT ------------------ #
ValidatorAgent = Agent(
    role="Admissions Document Validator",
    goal="Validate applicant documents against strict admission criteria",
    backstory=(
        "As a meticulous admissions validator, you ensure all applications meet "
        "strict technical requirements before proceeding to academic evaluation."
    ),
    tools=[DocumentValidatorTool()],
    memory=True,
    verbose=True
)

# ------------------ TASK ------------------ #
ValidationTask = Task(
    description=(
        "Process all applications needing validation checks. "
        "This includes both new applications and edited previously validated ones."
    ),
    expected_output=(
        "Database updated with validation status and detailed "
        "validation results in student.json"
    ),
    agent=ValidatorAgent,
    output_file="validation_report.txt"
)

# ------------------ CREW ------------------ #
def run_validator_crew():
    crew = Crew(
        agents=[ValidatorAgent],
        tasks=[ValidationTask],
        verbose=True
    )
    result = crew.kickoff(inputs={"trigger": "start"})
    print("Validation Process Complete:\n", result)

if __name__ == "__main__":
    # Initialize database schema if needed
   
    
    run_validator_crew()