import psycopg2
from airflow.utils.email import send_email

print("CALLBACKS.PY IS BEING IMPORTED!")

def on_failure_callback(context):
    task_instance = context['task_instance']
    failed_task_id = task_instance.task_id
    dag_id = context['dag'].dag_id
    exception = context.get('exception', 'error_message')
    run_id = task_instance.run_id if hasattr(task_instance, 'run_id') else 'unknown'

    print(f"Doctor Called! Task Failed: {dag_id}.{failed_task_id}")
    print(f"Error: {exception}")

    # 1. CHECK FOR MATCH IN DATABASE (RERUN LOGIC)
    try:
        conn = psycopg2.connect(host="postgres", database="airflow", user="airflow", password="airflow", port="5432")
        cursor = conn.cursor()
        
        # ONLY check if the exact error exists
        cursor.execute("SELECT solution_text FROM store_error WHERE error_text = %s LIMIT 1", (str(exception),))
        match = cursor.fetchone()
        
        if match:
            solution_text = match[0]
            print(f"FOUND MATCH: {solution_text}")
            print("AUTO-FIX APPLIED! Skipping email and rerunning task.")
            
            # Trigger a rerun. DO NOT update the solution_text, let it stay as the real solution!
            from rerun_engine import rerun_dag
            rerun_dag(dag_id, run_id)
            
            # IMPORTANT: Return here so we DO NOT send an email or escalate!
            cursor.close()
            conn.close()
            return
            
        else:
            print("NO MATCH FOUND. Escalating to human.")
            cursor.close()
            conn.close()

    except Exception as db_match_error:
        print(f"Failed to search for match: {db_match_error}")

    # 2. IF NO MATCH: SEND EMAIL & SAVE TO DASHBOARD
    try:
        conn = psycopg2.connect(host="postgres", database="airflow", user="airflow", password="airflow", port="5432")
        cursor = conn.cursor()
        
        cursor.execute("INSERT INTO store_error (error_text, solution_text) VALUES (%s, %s)", (str(exception), "Pending Review"))
        conn.commit()
        cursor.close()
        conn.close()
        print("Error pushed to Dashboard database")

    except Exception as db_error:
        print(f"Database check failed, proceeding with alert: {db_error}")

    # 3. SEND EMAIL
    try:
        DASHBOARD_URL = "http://localhost:8501"
        
        send_email(
            to="mariemsidi370@gmail.com",
            subject=f"[Airflow AI Ops] Task Escalated - Action Required",
            html_content=f"<h3>DAG: {dag_id}</h3><p>Task: {failed_task_id}</p><p>Error: {exception}</p><p>Run ID: {run_id}</p><p><strong>Dashboard:</strong> <a href='{DASHBOARD_URL}'>{DASHBOARD_URL}</a></p>"
        )
        print(f"UNIQUE EMAIL SENT TO mariemsidi370@gmail.com")
    except Exception as e:
        print(f"Failed to send email: {e}")