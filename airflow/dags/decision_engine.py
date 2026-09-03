import openai
import psycopg2
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Load Environment Variables
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# Database Connection Details
DB_CONN = {
    "host": "postgres",
    "database": "airflow",
    "user": "airflow",
    "password": "airflow",
    "port": "5432",
}

# Email Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SYSTEM_EMAIL = "mariemsidi370@gmail.com"     
SYSTEM_PASSWORD = "ehqm onqs pugr ewxy"      
RECIPIENT_EMAIL = "mariemsidi370@gmail.com"  
DASHBOARD_URL = "http://localhost:8501"

# Email Functions
def _send_email(subject, body):
    msg = MIMEMultipart()
    msg["From"] = SYSTEM_EMAIL
    msg["To"] = RECIPIENT_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SYSTEM_EMAIL, SYSTEM_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"Email sent to {RECIPIENT_EMAIL}: {subject}")
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

def send_rerun_notification(dag_id, task_id, run_id, confidence, solution):
    subject = "[Airflow AI Ops] Auto-Rerun Executed"
    body = f"""
DAG: {dag_id}
Task: {task_id}
Run ID: {run_id}
Confidence: {confidence:.2%}
Solution: {solution}
Status: Cleared and rerun successfully.
Dashboard: {DASHBOARD_URL}
"""
    _send_email(subject, body)

def send_escalation_notification(dag_id, task_id, run_id, confidence, error_log):
    subject = "[Airflow AI Ops] Task Escalated – Action Required"
    body = f"""
DAG: {dag_id}
Task: {task_id}
Run ID: {run_id}
Confidence: {confidence:.2%}
Error: {error_log[:200]}...
Dashboard: {DASHBOARD_URL}
"""
    _send_email(subject, body)

# Core Functions

def get_embedding(text):
    """Generate a 1536-dimensional embedding from OpenAI."""
    text = text.replace("\n", " ")
    response = openai.Embedding.create(
        input=text,
        model="text-embedding-3-small",
    )
    return response['data'][0]['embedding']

def build_prompt(current_error, similar_errors):
    """Build a prompt for the LLM with the current error and similar errors."""
    similar_text = ""
    for i, err in enumerate(similar_errors, 1):
        similar_text += f"""
        --- Similar Error {i} ---
        Error: {err['error_text']}
        Solution: {err['solution_text']}
        Similarity: {err['similarity']:.4f}
        """
    
    prompt = f"""
Analyze the following Airflow task failure and recommend the best action to take based on historical error patterns. Return it as JSON output.

Current Error:
{current_error}

Historical Context (similar past errors and their solutions):
{similar_text}

Decision Rules (use the highest similarity score to decide):
1. If the highest similarity is > 0.95 → recommend "rerun" with confidence > 0.95.
2. If the highest similarity is < 0.95 → recommend "escalate" with confidence < 0.5.

Your reasoning must explain:
- Which historical error is most similar and why.
- Why you chose "rerun" or "escalate" based on the similarity score.

Response Format (JSON only):
{{
    "action": "rerun" or "escalate",
    "confidence": 0.0 to 1.0,
    "reasoning": "Brief explanation of your decision",
    "suggested_solution": "Solution to apply" or null
}}

Please note that the data should be read by a JSON parser later.
"""
    return prompt

def call_llm(prompt):
    """Send the prompt to the OpenAI API and return the parsed response."""
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",  
        messages=[
            {"role": "system", "content": "You are an AI operations assistant for Apache Airflow. You analyze task failures and recommend actions."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        response_format={"type": "json_object"}
    )
    
    return json.loads(response.choices[0].message.content)

def search_similar(query_text: str, top_k: int = 3):  
    """Search for similar errors in the store_error table."""
    query_embedding = get_embedding(query_text)
    
    conn = psycopg2.connect(**DB_CONN)  
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT error_text, solution_text,
               1 - (embedding <=> %s::vector) AS similarity
        FROM store_error
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """, (str(query_embedding), str(query_embedding), top_k))
    
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return [
        {"error_text": r[0], "solution_text": r[1], "similarity": float(r[2])}
        for r in results
    ]

def make_decision(current_error):
    """Orchestrate the full decision-making process."""
    similar = search_similar(current_error, top_k=3)
    prompt = build_prompt(current_error, similar)
    decision = call_llm(prompt)
    return decision

def execute_decision(decision, dag_id, task_id, run_id):
    """
    Execute the decision made by the LLM.
    """
    action = decision.get('action')
    confidence = decision.get('confidence')
    suggested_solution = decision.get('suggested_solution', 'No solution available')
    error_log = decision.get('error_log', 'No error log available')
    
    RERUN_THRESHOLD = 0.95
    
    if action == 'rerun' and confidence >= RERUN_THRESHOLD:
        print(f"Executing rerun for task '{task_id}' with confidence {confidence:.2%}")
        
        try:
            from rerun_engine import clear_task
            clear_response = clear_task(dag_id, task_id, run_id)
            
            from rerun_engine import rerun_dag
            rerun_response = rerun_dag(dag_id, run_id)
            
            send_rerun_notification(dag_id, task_id, run_id, confidence, suggested_solution)
            
            return {
                'action': 'rerun',
                'confidence': confidence,
                'clear_response': clear_response,
                'rerun_response': rerun_response,
                'status': 'success'
            }
        except Exception as e:
            print(f"Error during rerun execution: {e}")
            return {
                'action': 'rerun',
                'confidence': confidence,
                'status': 'failed',
                'error': str(e)
            }
    else:
        print(f"Escalating task '{task_id}' for human review (confidence: {confidence:.2%})")
        
        send_escalation_notification(dag_id, task_id, run_id, confidence, error_log)
        
        return {
            'action': 'escalate',
            'confidence': confidence,
            'status': 'escalated',
            'message': 'Task escalated for human review'
        }

# Test the Function
if __name__ == "__main__":
    test_error = "KeyError: 'total_sales'"
    result = make_decision(test_error)
    print(json.dumps(result, indent=2))