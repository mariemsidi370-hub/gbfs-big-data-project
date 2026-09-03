"""
Station Status Pipeline 

GBFS station_status → MongoDB (bikes, docks, occupancy, live state).

Usage:
    python -m pipelines.station_status_pipeline
    python -m pipelines.station_status_pipeline --no-snapshot
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import datetime, timezone

import requests
from pymongo import MongoClient, UpdateOne

# --- Config ---
DEFAULT_STATION_STATUS_URL = (
    "https://velib-metropole-opendata.smovengo.cloud/opendata/"
    "Velib_Metropole/station_status.json"
)
STATION_STATUS_URL = os.getenv("GBFS_STATION_STATUS_URL", DEFAULT_STATION_STATUS_URL)
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "gbfs")
STATION_STATUS_COLLECTION = os.getenv("STATION_STATUS_COLLECTION", "station_status")
STATION_STATUS_SNAPSHOTS_COLLECTION = os.getenv(
    "STATION_STATUS_SNAPSHOTS_COLLECTION", "station_status_snapshots"
)
REQUEST_TIMEOUT_SECONDS = int(os.getenv("GBFS_REQUEST_TIMEOUT", "30"))

logger = logging.getLogger(__name__)


def _occupancy_rate(bikes, docks):
    """Share of bikes among bikes + free docks (live fill level)."""
    if bikes is None or docks is None:
        return None
    total = int(bikes) + int(docks)
    if total <= 0:
        return None
    return round(int(bikes) / total, 4)


# --- Fetch ---
def fetch_station_status(url=None) -> dict:
    feed_url = url or STATION_STATUS_URL
    logger.info("Fetching station status from %s", feed_url)

    response = requests.get(feed_url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    payload = response.json()
    if "data" not in payload or "stations" not in payload.get("data", {}):
        raise ValueError("Invalid GBFS station_status response: missing data.stations")

    logger.info(
        "Fetched %d station statuses (lastUpdated=%s, ttl=%s)",
        len(payload["data"]["stations"]),
        payload.get("lastUpdated") or payload.get("lastUpdatedOther"),
        payload.get("ttl"),
    )
    return payload


# --- Transform ---
def transform_status(raw: dict, feed_meta: dict, ingested_at=None) -> dict:
    ingested_at = ingested_at or datetime.now(timezone.utc)
    station_id = raw.get("station_id")
    if station_id is None:
        raise ValueError(f"Station status missing station_id: {raw}")

    bikes = raw.get("num_bikes_available")
    docks = raw.get("num_docks_available")

    return {
        "station_id": int(station_id),
        "num_bikes_available": bikes,
        "num_docks_available": docks,
        "occupancy_rate": _occupancy_rate(bikes, docks),
        "is_installed": raw.get("is_installed"),
        "is_renting": raw.get("is_renting"),
        "is_returning": raw.get("is_returning"),
        "last_reported": raw.get("last_reported"),
        "feed_last_updated": feed_meta.get("lastUpdated") or feed_meta.get("lastUpdatedOther"),
        "feed_ttl_seconds": feed_meta.get("ttl"),
        "ingested_at": ingested_at,
        "source": "velib_metropole",
    }


def transform_all(payload: dict, ingested_at=None) -> list:
    ingested_at = ingested_at or datetime.now(timezone.utc)
    feed_meta = {
        "lastUpdated": payload.get("lastUpdated"),
        "lastUpdatedOther": payload.get("lastUpdatedOther"),
        "ttl": payload.get("ttl"),
    }
    stations = payload["data"]["stations"]
    return [transform_status(s, feed_meta, ingested_at) for s in stations]


# --- Load ---
def get_mongo_client(uri=None) -> MongoClient:
    return MongoClient(uri or MONGO_URI)


def upsert_statuses(documents: list, *, mongo_uri=None, db_name=None, collection_name=None) -> dict:
    if not documents:
        return {"inserted": 0, "modified": 0, "matched": 0}

    client = get_mongo_client("mongodb://mongodb:27017/")
    coll = client[db_name or MONGO_DB][collection_name or STATION_STATUS_COLLECTION]

    operations = [
        UpdateOne({"station_id": doc["station_id"]}, {"$set": doc}, upsert=True)
        for doc in documents
    ]
    result = coll.bulk_write(operations, ordered=False)
    stats = {
        "inserted": result.upserted_count,
        "modified": result.modified_count,
        "matched": result.matched_count,
    }
    logger.info(
        "Upserted %d statuses into %s.%s — %s",
        len(documents),
        db_name or MONGO_DB,
        collection_name or STATION_STATUS_COLLECTION,
        stats,
    )
    client.close()
    return stats


def insert_snapshot(documents: list, *, mongo_uri=None, db_name=None, collection_name=None) -> str:
    ingested_at = datetime.now(timezone.utc)
    snapshot = {
        "ingested_at": ingested_at,
        "station_count": len(documents),
        "stations": documents,
        "source": "velib_metropole",
        "pipeline": "station_status",
    }

    client = get_mongo_client(mongo_uri)
    coll = client[db_name or MONGO_DB][collection_name or STATION_STATUS_SNAPSHOTS_COLLECTION]
    result = coll.insert_one(snapshot)
    logger.info(
        "Inserted snapshot %s with %d statuses into %s.%s",
        result.inserted_id,
        len(documents),
        db_name or MONGO_DB,
        collection_name or STATION_STATUS_SNAPSHOTS_COLLECTION,
    )
    client.close()
    return str(result.inserted_id)


# --- Run (Phase 2 entry point) ---
def run_pipeline(*, save_snapshot: bool = True) -> dict:
    payload = fetch_station_status()
    documents = transform_all(payload)
    stats = upsert_statuses(documents)

    snapshot_id = None
    if save_snapshot:
        snapshot_id = insert_snapshot(documents)

    return {
        "stations_processed": len(documents),
        "upsert_stats": stats,
        "snapshot_id": snapshot_id,
    }


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="GBFS Station Status Pipeline")
    parser.add_argument(
        "--no-snapshot",
        action="store_true",
        help="Skip writing batch snapshot to station_status_snapshots",
    )
    args = parser.parse_args()

    try:
        result = run_pipeline(save_snapshot=not args.no_snapshot)
        logger.info("Pipeline completed: %s", result)
        return 0
    except Exception:
        logger.exception("Station status pipeline failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
