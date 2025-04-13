import json
import datetime
import os
import base64
from dotenv import load_dotenv
from crewai import Agent, Task, Crew
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from email.mime.text import MIMEText

# -------------------------
# Load Environment Variables
# -------------------------
load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY  # For LiteLLM if used by CrewAI

# -------------------------
# Gmail Authentication
# -------------------------
SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def authenticate_gmail():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

# -------------------------
# Send Email
# -------------------------
def send_email(service, to, subject, body):
    message = MIMEText(body)
    message['to'] = to
    message['subject'] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    message = {'raw': raw}
    sent_message = service.users().messages().send(userId="me", body=message).execute()
    print(f"> ✅ Sent email to {to} (ID: {sent_message['id']})")

# -------------------------
# Logging Function
# -------------------------
def log_to_file(data, log_file="email_log.json"):
    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            logs = json.load(f)
    else:
        logs = []
    logs.append(data)
    with open(log_file, "w") as f:
        json.dump(logs, f, indent=4)

# -------------------------
# Generate Email using CrewAI
# -------------------------
def generate_email_body(student):
    communicator = Agent(
        role="Admission Communicator",
        goal="Write short and polite emails to students regarding their admission status",
        backstory="You assist the admission office by notifying students about their application outcomes.",
        verbose=True,
        allow_delegation=False,
        tools=[],
        llm="gpt-4"
    )

    issue_text = (
        f"However, we found the following issues with your documents: {', '.join(student['issues'])}. "
        "Kindly resubmit the corrected documents within 2 days to proceed further."
        if student["issues"]
        else "Your application was processed without any issues."
    )

    task = Task(
        description=(
            f"Write a short, polite and professional email to a student regarding their admission status.\n\n"
            f"Student Email: {student['email']}\n"
            f"Status: {student['status'].capitalize()}\n"
            f"{issue_text}\n\n"
            "End the email with:\nAdmission Cell\nIEM Kolkata"
        ),
        expected_output="A concise email body (no subject) with proper sign-off.",
        agent=communicator
    )

    crew = Crew(agents=[communicator], tasks=[task], verbose=True)
    result = crew.kickoff()

    return str(result).strip()  # 🧯 FIXED LINE

# -------------------------
# Main Workflow
# -------------------------
def run_communicator_pipeline():
    with open("students.json", "r") as f:
        validator_output = json.load(f)

    service = authenticate_gmail()

    for student in validator_output:
        print(f"\n📨 Processing email for: {student['email']}")

        email_body = generate_email_body(student)
        send_email(service, student["email"], "Your Application Status", email_body)

        log_data = {
            "email": student["email"],
            "status": student["status"],
            "issues": student["issues"],
            "timestamp": datetime.datetime.now().isoformat()
        }
        log_to_file(log_data)

# -------------------------
# Entry Point
# -------------------------
if __name__ == "__main__":
    run_communicator_pipeline()
