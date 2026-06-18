from langchain_core.prompts import ChatPromptTemplate
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from typing import TypedDict
import os
import gspread
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib
from dotenv import load_dotenv

load_dotenv()

model = ChatOpenAI()

CREDS_FILE = os.getenv("GOOGLE_CREDS_FILE", "credentials.json")
SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME", "Job Applications")


class State(TypedDict):
    receiver_address : str
    company : str
    role : str
    row_number: int
    email_body : str
    email_subject: str
    job_desc : str
    email_sent: bool
    has_pending: bool


def fetch_next_pending_row(state: State) -> State:
    """Fetch the next pending row from Google Sheet and load it into state."""
    gc = gspread.service_account(filename=CREDS_FILE)
    sheet = gc.open(SHEET_NAME).sheet1
    rows = sheet.get_all_records()

    for idx, row in enumerate(rows, start=2):
        if str(row["email_sent"]).lower() == "false":
            state['company'] = row["Company"]
            state['receiver_address'] = row["Email"]
            state['job_desc'] = row["Description"]
            state['role'] = row["Role"]
            state['row_number'] = idx
            state['email_sent'] = False
            state['has_pending'] = True
            print(f"\n📨 Processing: {row['Company']} — {row['Role']}")
            return state

    state['has_pending'] = False
    print("\n🎉 All pending applications processed!")
    return state


def generate_email(state: State) -> State:
    """Generate email"""
    resume_path = os.getenv("RESUME_PATH")
    job_desc = state['job_desc']
    company = state['company']
    role = state['role']
    System_prompt = """You are a professional job application email writer.

Generate a concise, personalized, and human-like job application email in JSON format with the following keys:

{{
"subject": "...",
"body": "..."
}}

Candidate Information:

* Name: Priyanshu Khandelwal
* Strong Python developer with experience in AI engineering and full-stack development
* Experienced with LangChain, LangGraph, RAG systems, AI Agents, LLM integrations, OpenAI APIs, Google APIs, and workflow automation
* Worked PetAlly, an AI-powered pet healthcare platform featuring multi-agent veterinary assistance and online vet consultation
* Developed AI-powered applications involving document processing, data extraction, and automation workflows
* Comfortable with Python, SQL, FastAPI, Flask, PostgreSQL, Docker
* Passionate about Generative AI, Agentic AI Systems, and applied machine learning

Email Requirements:

1. Write as the candidate directly.
2. Keep the email between 120 and 180 words.
3. Maintain a professional, confident, and natural tone.
4. Avoid sounding AI-generated or overly formal.
5. Mention only the most relevant experience based on the provided job description.
6. Highlight LangChain, LangGraph, RAG, AI Agents, or PetAlly only when relevant to the role.
7. Explain briefly why the candidate is a strong fit.
8. End with a short call-to-action expressing interest in discussing the opportunity.
9. Do not include placeholders like [Your Name].
10. Generate a personalized subject line specific to the company and role.

Return only valid JSON.
"""
    prompt = ChatPromptTemplate.from_messages([
        ("system", System_prompt),
        ("human", "Resume: {resume_path}\n\nJob Description: {job_desc}\n\nCompany: {company}\n\nRole: {role}")
    ])

    parser = JsonOutputParser()
    chain = prompt | model | parser
    response = chain.invoke({
        "resume_path": resume_path,
        "job_desc": job_desc,
        "company": company,
        "role": role
    })

    state['email_body'] = response['body']
    state['email_subject'] = response['subject']
    return state


def send_email(state: State) -> State:
    """send email via Gmail SMTP with resume PDF attached"""
    from email.mime.application import MIMEApplication

    receiver_address = state['receiver_address']
    email_body = state['email_body']
    email_subject = state['email_subject']
    resume_path = os.getenv("RESUME_PATH")
    sender_email = os.getenv("EMAIL")
    sender_password = os.getenv("GOOGLE_APP_PASSWORD")

    # --- Error handling: missing env vars ---
    if not sender_email or not sender_password:
        print("❌ Error: EMAIL or GOOGLE_APP_PASSWORD not set in .env")
        state['email_sent'] = False
        return state

    if not receiver_address:
        print("❌ Error: No receiver address provided")
        state['email_sent'] = False
        return state

    if not resume_path:
        print("❌ Error: RESUME_PATH not set in .env")
        state['email_sent'] = False
        return state

    # --- Error handling: resume file exists ---
    if not os.path.exists(resume_path):
        print(f"❌ Error: Resume file not found at '{resume_path}'")
        state['email_sent'] = False
        return state

    # --- Build email ---
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_address
    msg['Subject'] = email_subject
    msg.attach(MIMEText(email_body, 'plain'))

    # --- Attach resume PDF ---
    try:
        with open(resume_path, 'rb') as f:
            pdf = MIMEApplication(f.read(), _subtype='pdf')
            pdf.add_header('Content-Disposition', 'attachment', filename=os.path.basename(resume_path))
            msg.attach(pdf)
    except Exception as e:
        print(f"❌ Error reading resume file: {e}")
        state['email_sent'] = False
        return state

    # --- Send email ---
    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.sendmail(sender_email, receiver_address, msg.as_string())
        print(f"✅ Email sent successfully to {receiver_address}")
        state['email_sent'] = True
    except smtplib.SMTPAuthenticationError:
        print("❌ Error: SMTP auth failed. Check EMAIL and GOOGLE_APP_PASSWORD.")
        state['email_sent'] = False
    except smtplib.SMTPRecipientsRefused:
        print(f"❌ Error: Recipient refused — invalid address: {receiver_address}")
        state['email_sent'] = False
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        state['email_sent'] = False

    # --- Update Google Sheet with email status ---
    try:
        gc = gspread.service_account(filename=CREDS_FILE)
        sheet = gc.open(SHEET_NAME).sheet1

        row_number = state.get('row_number')
        if row_number:
            headers = sheet.row_values(1)
            status_col = headers.index("email_sent") + 1

            if state['email_sent']:
                sheet.update_cell(row_number, status_col, "TRUE")
                print(f"📝 Sheet updated: row {row_number} → email_sent = TRUE")
            else:
                sheet.update_cell(row_number, status_col, "FALSE")
                print(f"📝 Sheet updated: row {row_number} → email_sent = FALSE")
        else:
            print("⚠️ Warning: No row_number in state, skipping sheet update")
    except Exception as e:
        print(f"❌ Error updating sheet: {e}")

    return state


# --- Conditional edge: check if there are more pending rows ---
def should_continue(state: State) -> str:
    """Route to generate_email if pending rows exist, otherwise end."""
    if state.get('has_pending'):
        return "generate_email"
    return END


# --- Build the LangGraph ---
graph = StateGraph(State)

# Add nodes
graph.add_node("fetch_data", fetch_next_pending_row)
graph.add_node("generate_email", generate_email)
graph.add_node("send_email", send_email)

# Add edges
graph.add_edge(START, "fetch_data")
graph.add_conditional_edges("fetch_data", should_continue, {"generate_email": "generate_email", END: END})
graph.add_edge("generate_email", "send_email")
graph.add_edge("send_email", "fetch_data")  # Loop back to check for more

# Compile
app = graph.compile()


if __name__ == "__main__":
    result = app.invoke({})
    print("\n✅ Final state:", result)
