from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import requests
from pymongo import MongoClient
import logging

# Default arguments for the DAG
default_args = {
    'owner': 'idriss',
    'depends_on_past': False,
    'start_date': datetime(2026, 5, 29),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# Function to fetch station info
def fetch_and_store_station_info():
    """Fetch station information from GBFS API and store in MongoDB"""
    
    # API endpoint
    url = "https://velib-metropole-opendata.smovengo.cloud/opendata/Velib_Metropole/station_information.json"
    
    # MongoDB connection
    mongo_client = MongoClient("mongodb://mongodb:27017/")
    db = mongo_client["gbfs"]
    collection = db["station_info"]
    
    try:
        # Fetch data
        logging.info("Fetching station info from API...")
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Extract stations
        stations = data.get("data", {}).get("stations", [])
        logging.info(f"Fetched {len(stations)} stations")
        
        # Add timestamp
        for station in stations:
            station["last_updated"] = datetime.now()
        
        # Clear existing and insert new
        collection.delete_many({})
        result = collection.insert_many(stations)
        
        logging.info(f"Stored {len(result.inserted_ids)} stations in MongoDB")
        
    except Exception as e:
        logging.error(f"Error: {e}")
        raise
    finally:
        mongo_client.close()

# Define the DAG
dag = DAG(
    'station_info_pipeline',
    default_args=default_args,
    description='Fetch station information from GBFS API',
    schedule_interval='@weekly',  # Runs once per week
    catchup=False,
    tags=['gbfs', 'station_info'],
)

# Define the task
fetch_station_info_task = PythonOperator(
    task_id='fetch_and_store_station_info',
    python_callable=fetch_and_store_station_info,
    dag=dag,
)

fetch_station_info_task