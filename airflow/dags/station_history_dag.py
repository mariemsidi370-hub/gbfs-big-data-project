from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.operators.python import PythonOperator
import logging

# Default arguments for the DAG
default_args = {
    'owner': 'idriss',
    'depends_on_past': False,
    'start_date': datetime(2026, 5, 31),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Function to run the historical pipeline
def run_historical_pipeline():
    """Run the historical data pipeline"""
    import sys
    from pathlib import Path
    
    # Add pipelines folder to path
    pipelines_path = Path("/opt/airflow/pipelines")
    if str(pipelines_path) not in sys.path:
        sys.path.insert(0, str(pipelines_path))
    
    from station_history_pipeline import run_pipeline
    
    logging.info("Starting Historical Data Pipeline from Airflow DAG")
    result = run_pipeline()
    logging.info(f"Historical Pipeline completed: {result}")
    return result

# Define the DAG
dag = DAG(
    'station_history_pipeline',
    default_args=default_args,
    description='Aggregate historical trends from station status data',
    schedule_interval='@daily',  # Runs once per day
    catchup=False,
    tags=['gbfs', 'historical', 'analytics'],
)

# Task 1: Run the historical pipeline
run_history_task = PythonOperator(
    task_id='run_historical_pipeline',
    python_callable=run_historical_pipeline,
    dag=dag,
)

# Optional: Task to verify the data was created
def verify_history_data():
    from pymongo import MongoClient
    client = MongoClient("mongodb://mongodb:27017/")
    db = client["gbfs"]
    count = db.station_history.count_documents({})
    logging.info(f"Station history collection has {count} records")
    client.close()
    if count == 0:
        raise ValueError("No historical records found!")

verify_task = PythonOperator(
    task_id='verify_history_data',
    python_callable=verify_history_data,
    dag=dag,
)

# Set dependencies
run_history_task >> verify_task