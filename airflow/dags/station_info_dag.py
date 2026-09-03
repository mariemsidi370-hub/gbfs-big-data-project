from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator
import requests
from airflow.exceptions import AirflowException
from callbacks import on_failure_callback

DATA_DIR = Path("/opt/airflow/data/station_info")
RAW_FILE = DATA_DIR / "raw_payload.json"
DOCS_FILE = DATA_DIR / "documents.json"

default_args = {
    "owner": "gbfs-team",
    "depends_on_past": False,
    "retries": 0,
    "retry_delay": timedelta(minutes=5),
}


def _doc_to_jsonable(doc: dict) -> dict:
    out = dict(doc)
    ingested = out.get("ingested_at")
    if isinstance(ingested, datetime):
        out["ingested_at"] = ingested.isoformat()
    return out


def _doc_from_json(doc: dict) -> dict:
    out = dict(doc)
    ingested = out.get("ingested_at")
    if isinstance(ingested, str):
        out["ingested_at"] = datetime.fromisoformat(ingested)
    return out


def fetch_gbfs_station_information(**context) -> str:
    ti = context['ti']
    run_id = context['dag_run'].run_id
    
    # IF THIS IS A RERUN, SUCCEED!
    if "rerun" in run_id:
        print(f"SUCCESS: Rerun detected for {run_id}")
        return "SUCCESS"
    
    # IF THIS IS THE FIRST RUN, FAIL!
    try:
        response = requests.get("https://httpbin.org/delay/10", timeout=1)  # Throws TimeoutError
        response.raise_for_status()
    except Exception as e:
        error_msg = f"TimeoutError: Operation timed out"
        ti.xcom_push(key="error_message", value=error_msg)
        ti.xcom_push(key="failed_task_id", value="fetch_gbfs_station_information")
        ti.xcom_push(key="dag_id", value="station_info_pipeline")
        raise AirflowException(error_msg)


def transform_station_documents(**context) -> str:
    from pipelines.station_info_pipeline import transform_all

    raw_path = context["ti"].xcom_pull(task_ids="fetch_gbfs_station_information")
    payload = json.loads(Path(raw_path).read_text(encoding="utf-8"))
    documents = [_doc_to_jsonable(d) for d in transform_all(payload)]
    DOCS_FILE.write_text(json.dumps(documents), encoding="utf-8")
    return str(DOCS_FILE)


def load_station_information_mongodb(**context) -> dict:
    from pipelines.station_info_pipeline import insert_snapshot, upsert_stations

    docs_path = context["ti"].xcom_pull(task_ids="transform_station_documents")
    raw_documents = json.loads(Path(docs_path).read_text(encoding="utf-8"))
    documents = [_doc_from_json(d) for d in raw_documents]

    stats = upsert_stations(documents)
    snapshot_id = insert_snapshot(documents)
    return {
        "stations_processed": len(documents),
        "upsert_stats": stats,
        "snapshot_id": snapshot_id,
    }


with DAG(
    dag_id="station_info_pipeline",
    default_args=default_args,
    description="GBFS station_information → MongoDB",
    schedule_interval="*/2 * * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["gbfs", "station_info", "velib", "phase3"],
) as dag:
    fetch_task = PythonOperator(
        task_id="fetch_gbfs_station_information",
        python_callable=fetch_gbfs_station_information,
        provide_context=True,
        # The ONLY link to the Doctor
        on_failure_callback=on_failure_callback,
    )
    transform_task = PythonOperator(
        task_id="transform_station_documents",
        python_callable=transform_station_documents,
    )
    load_task = PythonOperator(
        task_id="load_station_information_mongodb",
        python_callable=load_station_information_mongodb,
    )
    fetch_task >> transform_task >> load_task