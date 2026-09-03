import requests
import json
import time
import hashlib

# Base URL for Airflow REST API (use the service name inside Docker)
# NOTE: In the airflow-ai-ops container, the webserver is accessible as "airflow-webserver"
AIRFLOW_API_URL = "http://airflow-webserver:8080/api/v1"

# Authentication (basic auth as configured in your docker-compose.yml)
AUTH = ('admin', 'admin')

def clear_task(dag_id, task_id, run_id):
    """
    Clear a failed task instance using Airflow's REST API.
    
    Args:
        dag_id (str): The ID of the DAG.
        task_id (str): The ID of the task to clear.
        run_id (str): The ID of the DAG run.
    
    Returns:
        dict: The API response.
    """
    url = f"{AIRFLOW_API_URL}/dags/{dag_id}/clearTaskInstances"
    
    payload = {
        "dry_run": False,
        "task_ids": [task_id],
        "dag_run_id": run_id,
        "only_failed": True,
        "include_downstream": False,
        "include_upstream": False,
        "include_future": False,
        "include_past": False
    }
    
    response = requests.post(url, json=payload, auth=AUTH)
    
    if response.status_code == 200:
        print(f"Task '{task_id}' cleared successfully.")
        return response.json()
    else:
        print(f"Error clearing task: {response.status_code} - {response.text}")
        response.raise_for_status()

def rerun_dag(dag_id, run_id):
    """
    Trigger a new DAG run using Airflow's REST API.
    
    Args:
        dag_id (str): The ID of the DAG.
        run_id (str): The original DAG run ID (used to generate a new unique ID).
    
    Returns:
        dict: The API response.
    """
    url = f"{AIRFLOW_API_URL}/dags/{dag_id}/dagRuns"
    
    # Generate a short, unique new run_id
    import time
    import hashlib
    short_hash = hashlib.md5(run_id.encode()).hexdigest()[:8]
    new_run_id = f"rerun_{short_hash}_{int(time.time())}"
    
    payload = {
        "dag_run_id": new_run_id,
        "conf": {}
    }
    
    response = requests.post(url, json=payload, auth=AUTH)
    
    if response.status_code == 200:
        print(f"DAG '{dag_id}' rerun triggered successfully with run_id: {new_run_id}")
        return response.json()
    else:
        print(f"Error triggering DAG run: {response.status_code} - {response.text}")
        response.raise_for_status()