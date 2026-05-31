"""
Station Information Pipeline — Phase 2 + 3 (single module).

GBFS station_information → MongoDB (names, coords, capacity).

Usage:
    python -m pipelines.station_info_pipeline
    python -m pipelines.station_info_pipeline --no-snapshot
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
DEFAULT_STATION_INFO_URL = (
    "https://velib-metropole-opendata.smovengo.cloud/opendata/"
    "Velib_Metropole/station_information.json"
)
STATION_INFO_URL = os.getenv("GBFS_STATION_INFO_URL", DEFAULT_STATION_INFO_URL)
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "gbfs")
STATION_INFO_COLLECTION = os.getenv("STATION_INFO_COLLECTION", "station_information")
STATION_INFO_SNAPSHOTS_COLLECTION = os.getenv(
    "STATION_INFO_SNAPSHOTS_COLLECTION", "station_information_snapshots"
)
REQUEST_TIMEOUT_SECONDS = int(os.getenv("GBFS_REQUEST_TIMEOUT", "30"))

logger = logging.getLogger(__name__)


# --- Fetch ---
def fetch_station_information(url=None) -> dict:
    feed_url = url or STATION_INFO_URL
    logger.info("Fetching station information from %s", feed_url)

    response = requests.get(feed_url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()

    payload = response.json()
    if "data" not in payload or "stations" not in payload.get("data", {}):
        raise ValueError(
            "Invalid GBFS station_information response: missing data.stations"
        )

    logger.info(
        "Fetched %d stations (lastUpdatedOther=%s, ttl=%s)",
        len(payload["data"]["stations"]),
        payload.get("lastUpdatedOther"),
        payload.get("ttl"),
    )
    return payload


# --- Transform ---
def _normalize_rental_methods(value):
    if value is None:
        return None
    if isinstance(value, list):
        return [str(m) for m in value]
    return [str(value)]


def transform_station(raw: dict, feed_meta: dict, ingested_at=None) -> dict:
    ingested_at = ingested_at or datetime.now(timezone.utc)
    station_id = raw.get("station_id")
    if station_id is None:
        raise ValueError(f"Station missing station_id: {raw}")

    return {
        "station_id": int(station_id),
        "station_code": str(raw.get("stationCode", "")),
        "name": raw.get("name"),
        "lat": float(raw["lat"]) if raw.get("lat") is not None else None,
        "lon": float(raw["lon"]) if raw.get("lon") is not None else None,
        "capacity": raw.get("capacity"),
        "rental_methods": _normalize_rental_methods(raw.get("rental_methods")),
        "station_opening_hours": raw.get("station_opening_hours"),
        "feed_last_updated": feed_meta.get("lastUpdatedOther"),
        "feed_ttl_seconds": feed_meta.get("ttl"),
        "ingested_at": ingested_at,
        "source": "velib_metropole",
    }


def transform_all(payload: dict, ingested_at=None) -> list:
    ingested_at = ingested_at or datetime.now(timezone.utc)
    feed_meta = {
        "lastUpdatedOther": payload.get("lastUpdatedOther"),
        "ttl": payload.get("ttl"),
    }
    stations = payload["data"]["stations"]
    return [transform_station(s, feed_meta, ingested_at) for s in stations]


# --- Load ---
def get_mongo_client(uri=None) -> MongoClient:
    return MongoClient(uri or MONGO_URI)


def upsert_stations(documents: list, *, mongo_uri=None, db_name=None, collection_name=None) -> dict:
    if not documents:
        return {"inserted": 0, "modified": 0, "matched": 0}

    client = get_mongo_client(mongo_uri)
    coll = client[db_name or MONGO_DB][collection_name or STATION_INFO_COLLECTION]

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
        "Upserted %d stations into %s.%s — %s",
        len(documents),
        db_name or MONGO_DB,
        collection_name or STATION_INFO_COLLECTION,
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
        "pipeline": "station_info",
    }

    client = get_mongo_client(mongo_uri)
    coll = client[db_name or MONGO_DB][collection_name or STATION_INFO_SNAPSHOTS_COLLECTION]
    result = coll.insert_one(snapshot)
    logger.info(
        "Inserted snapshot %s with %d stations into %s.%s",
        result.inserted_id,
        len(documents),
        db_name or MONGO_DB,
        collection_name or STATION_INFO_SNAPSHOTS_COLLECTION,
    )
    client.close()
    return str(result.inserted_id)


# --- Run (Phase 2 entry point) ---
def run_pipeline(*, save_snapshot: bool = True) -> dict:
    payload = fetch_station_information()
    documents = transform_all(payload)
    stats = upsert_stations(documents)

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
    parser = argparse.ArgumentParser(description="GBFS Station Information Pipeline")
    parser.add_argument(
        "--no-snapshot",
        action="store_true",
        help="Skip writing batch snapshot to station_information_snapshots",
    )
    args = parser.parse_args()

    try:
        result = run_pipeline(save_snapshot=not args.no_snapshot)
        logger.info("Pipeline completed: %s", result)
        return 0
    except Exception:
        logger.exception("Station info pipeline failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
