"""Historical Data Pipeline - Aggregates trends from station status data."""
import argparse
import logging
from datetime import datetime
from pymongo import MongoClient, ASCENDING, DESCENDING
from collections import defaultdict

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

MONGO_URI = "mongodb://mongodb:27017/"
MONGO_DB = "gbfs"

def get_collections():
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    return client, db["station_status"], db["station_history"]

def calculate_station_averages(status_collection):
    """Calculate average bikes and docks per station"""
    pipeline = [
        {"$group": {
            "_id": "$station_id",
            "avg_bikes_available": {"$avg": "$num_bikes_available"},
            "avg_docks_available": {"$avg": "$num_docks_available"},
            "total_snapshots": {"$sum": 1},
            "last_seen": {"$max": "$timestamp"}
        }}
    ]
    results = list(status_collection.aggregate(pipeline))
    logger.info(f"Calculated averages for {len(results)} stations")
    return results

def calculate_peak_hours(status_collection):
    """Calculate peak hours (hour with most bikes taken)"""
    pipeline = [
        {"$addFields": {"hour": {"$hour": "$timestamp"}}},
        {"$group": {
            "_id": {"station_id": "$station_id", "hour": "$hour"},
            "avg_bikes_available": {"$avg": "$num_bikes_available"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id.station_id": 1, "avg_bikes_available": 1}},
        {"$group": {
            "_id": "$_id.station_id",
            "peak_hour": {"$first": "$_id.hour"},
            "min_bikes_hour": {"$first": "$avg_bikes_available"},
            "peak_hour_count": {"$first": "$count"}
        }}
    ]
    results = list(status_collection.aggregate(pipeline))
    logger.info(f"Calculated peak hours for {len(results)} stations")
    return {r["_id"]: {"peak_hour": r["peak_hour"], "min_bikes": r["min_bikes_hour"]} for r in results}

def store_historical_results(history_collection, averages, peak_hours):
    """Store aggregated results in station_history collection"""
    operations = []
    for avg in averages:
        station_id = avg["_id"]
        doc = {
            "station_id": station_id,
            "avg_bikes_available": round(avg["avg_bikes_available"], 2),
            "avg_docks_available": round(avg["avg_docks_available"], 2),
            "total_snapshots": avg["total_snapshots"],
            "last_seen": avg["last_seen"],
            "peak_hour": peak_hours.get(station_id, {}).get("peak_hour"),
            "min_bikes_at_peak": peak_hours.get(station_id, {}).get("min_bikes"),
            "last_calculated": datetime.now()
        }
        operations.append(doc)
    
    if operations:
        history_collection.delete_many({})
        result = history_collection.insert_many(operations)
        logger.info(f"Stored {len(result.inserted_ids)} station historical records")
    return len(operations)

def run_pipeline():
    """Main pipeline execution"""
    logger.info("Starting Historical Data Pipeline")
    
    client, status_collection, history_collection = get_collections()
    
    try:
        total_status_records = status_collection.count_documents({})
        logger.info(f"Processing {total_status_records} status records")
        
        if total_status_records == 0:
            logger.warning("No status records found. Run station_status_pipeline first.")
            return {"error": "No status data available"}
        
        averages = calculate_station_averages(status_collection)
        peak_hours = calculate_peak_hours(status_collection)
        stored_count = store_historical_results(history_collection, averages, peak_hours)
        
        logger.info(f"Historical Pipeline completed. Stored {stored_count} records.")
        return {"stations_processed": len(averages), "records_stored": stored_count}
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise
    finally:
        client.close()

def main():
    parser = argparse.ArgumentParser(description="Station History Pipeline")
    parser.add_argument("--no-snapshot", action="store_true", help="Skip snapshot creation")
    args = parser.parse_args()
    
    result = run_pipeline()
    logger.info(f"Pipeline completed: {result}")

if __name__ == "__main__":
    main()