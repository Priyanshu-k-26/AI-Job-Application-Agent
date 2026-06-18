# AI Job Application Agent

An automated job application agent built using [LangGraph](https://python.langchain.com/docs/langgraph), LangChain, and OpenAI. 

This agent automatically reads pending job applications from a Google Sheet, uses an LLM to generate a tailored and professional email body and subject line, attaches your resume PDF, and sends the email via Gmail SMTP. After sending the email successfully, it updates the Google Sheet to mark the application as "sent".

## Features
- **LangGraph Orchestration**: Uses LangGraph's state machine to manage the flow of fetching data, generating emails, and sending them.
- **Google Sheets Integration**: Automatically fetches rows marked as `pending` or `FALSE` for `email_sent` and updates them after processing.
- **AI-Powered Emails**: Leverages OpenAI models via LangChain to generate contextual emails based on the specific job description and company.
- **Automated Email Sending**: Connects via Gmail SMTP to dispatch emails with your resume attached natively as a PDF.

## Prerequisites
- Python 3.9+
- A Google Cloud Project with the **Google Sheets API** and **Google Drive API** enabled.
- A Google Service Account JSON credentials file.
- An OpenAI API Key.
- A Gmail account with an **App Password** generated (2-Step Verification required).

## Setup & Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/Priyanshu-k-26/AI-Job-Application-Agent.git
   cd AI-Job-Application-Agent
   ```

2. **Create a virtual environment and install dependencies:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure Google Sheets:**
   - Create a Google Sheet with the following headers (case-sensitive):
     `Email`, `Description`, `Role`, `email_sent`, `Company`
   - Share the Google Sheet with the `client_email` found in your Service Account JSON file (give it Editor access).

4. **Environment Variables:**
   Create a `.env` file in the root directory and add the following keys:
   ```env
   OPENAI_API_KEY=your_openai_api_key
   EMAIL=your_gmail_address@gmail.com
   GOOGLE_APP_PASSWORD=your_16_character_gmail_app_password
   GOOGLE_SHEET_NAME=your_google_sheet_name
   GOOGLE_CREDS_FILE=path_to_your_service_account.json
   RESUME_PATH=path_to_your_resume.pdf
   ```

5. **Add your resume and credentials:**
   Place your resume PDF and Google service account JSON file in the project directory (ensure they match the names provided in the `.env` file).

## Usage
Run the agent using Python:
```bash
python app.py
```

The script will:
1. Connect to the Google Sheet and find the first pending application.
2. Generate a custom email using OpenAI.
3. Send the email with the resume attached.
4. Update the Google Sheet's `email_sent` column to `TRUE`.
5. Repeat until all pending applications are processed.
