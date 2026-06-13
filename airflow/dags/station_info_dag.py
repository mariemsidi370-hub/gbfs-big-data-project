
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator

DATA_DIR = Path("/opt/airflow/data/station_info")
RAW_FILE = DATA_DIR / "raw_payload.json"
DOCS_FILE = DATA_DIR / "documents.json"

default_args = {
    "owner": "gbfs-team",
    "depends_on_past": False,
    "retries": 2,
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


def fetch_gbfs_station_information() -> str:
    from pipelines.station_info_pipeline import fetch_station_information

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = fetch_station_information()
    RAW_FILE.write_text(json.dumps(payload), encoding="utf-8")
    return str(RAW_FILE)


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
    schedule_interval="0 */6 * * *",
    start_date=datetime(2026, 5, 1),
    catchup=False,
    tags=["gbfs", "station_info", "velib", "phase3"],
) as dag:
    fetch_task = PythonOperator(
        task_id="fetch_gbfs_station_information",
        python_callable=fetch_gbfs_station_information,
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
