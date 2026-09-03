from __future__ import annotations
import json
from datetime import datetime, timedelta
from pathlib import Path
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.exceptions import AirflowException

from callbacks import on_failure_callback

default_args = {
    "owner": "gbfs-team",
    "depends_on_past": False,
    "retries": 0,
    "retry_delay": timedelta(minutes=1),
}

def flaky_fetch(**context):
    ti = context['ti']
    try:
        import requests
        # FIXED: Changed the invalid URL to the real Vélib API
        response = requests.get("https://velib-metropole-opendata.smovengo.cloud/opendata/Velib_Metropole/station_status.json", timeout=10)
        response.raise_for_status()
    except Exception as e:
        error_msg = f"ConnectionError: Failed to reach API at http://invalid-url-for-testing:9999"
        ti.xcom_push(key="error_message", value=error_msg)
        ti.xcom_push(key="failed_task_id", value="fetch_gbfs_station_status")
        ti.xcom_push(key="dag_id", value="station_status_pipeline")
        raise AirflowException(error_msg)

with DAG(
    dag_id="station_status_pipeline",
    default_args=default_args,
    schedule_interval="*/2 * * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
) as dag:
    fetch_task = PythonOperator(
        task_id="fetch_gbfs_station_status",
        python_callable=flaky_fetch,
        provide_context=True,
        on_failure_callback=on_failure_callback,
    )