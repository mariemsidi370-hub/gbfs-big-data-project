"""Historical Data Pipeline , Aggregates trends from station status data."""
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


#

def calculate_global_kpis(status_collection, info_collection):
    """Calculate global KPIs for dashboard"""
    
    # 1. Total stations
    total_stations = info_collection.count_documents({})
    
    # 2. Current bikes available (latest snapshot)
    latest_snapshot = list(status_collection.find().sort("ingested_at", -1).limit(1))
    if latest_snapshot:
        all_statuses = list(status_collection.find({"ingested_at": latest_snapshot[0]["ingested_at"]}))
        total_bikes_now = sum(s.get("num_bikes_available", 0) for s in all_statuses)
        total_docks_now = sum(s.get("num_docks_available", 0) for s in all_statuses)
        avg_occupancy_now = total_bikes_now / (total_bikes_now + total_docks_now) if (total_bikes_now + total_docks_now) > 0 else 0
    else:
        total_bikes_now = 0
        avg_occupancy_now = 0
    
    # 3. Empty stations (0 bikes)
    empty_stations = status_collection.count_documents({"num_bikes_available": 0})
    
    # 4. Full stations (bikes >= capacity - 2)
    pipeline_full = [
        {"$lookup": {
            "from": "station_information",
            "localField": "station_id",
            "foreignField": "station_id",
            "as": "info"
        }},
        {"$match": {
            "$expr": {
                "$gte": ["$num_bikes_available", {"$subtract": [{"$arrayElemAt": ["$info.capacity", 0]}, 2]}]
            }
        }},
        {"$count": "full_stations"}
    ]
    full_result = list(status_collection.aggregate(pipeline_full))
    full_stations = full_result[0]["full_stations"] if full_result else 0
    
    return {
        "total_stations": total_stations,
        "total_bikes_now": total_bikes_now,
        "avg_occupancy_now": round(avg_occupancy_now * 100, 1),
        "empty_stations": empty_stations,
        "full_stations": full_stations,
        "last_update": datetime.now()
    }

def calculate_top_stations(status_collection, info_collection, limit=10):
    """Calculate top 10 stations with most bikes"""
    latest_snapshot = list(status_collection.find().sort("ingested_at", -1).limit(1))
    if not latest_snapshot:
        return []
    
    pipeline = [
        {"$match": {"ingested_at": latest_snapshot[0]["ingested_at"]}},
        {"$sort": {"num_bikes_available": -1}},
        {"$limit": limit},
        {"$lookup": {
            "from": "station_information",
            "localField": "station_id",
            "foreignField": "station_id",
            "as": "info"
        }},
        {"$project": {
            "station_id": 1,
            "num_bikes_available": 1,
            "num_docks_available": 1,
            "station_name": {"$arrayElemAt": ["$info.name", 0]},
            "capacity": {"$arrayElemAt": ["$info.capacity", 0]}
        }}
    ]
    return list(status_collection.aggregate(pipeline))

def calculate_occupancy_by_hour(status_collection):
    """Calculate average occupancy by hour of day"""
    pipeline = [
        {"$addFields": {"hour": {"$hour": "$timestamp"}}},
        {"$group": {
            "_id": "$hour",
            "avg_bikes": {"$avg": "$num_bikes_available"},
            "avg_docks": {"$avg": "$num_docks_available"},
            "sample_count": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    results = list(status_collection.aggregate(pipeline))
    
    hourly_data = []
    for r in results:
        total = r["avg_bikes"] + r["avg_docks"]
        occupancy = (r["avg_bikes"] / total * 100) if total > 0 else 0
        hourly_data.append({
            "hour": r["_id"],
            "avg_bikes": round(r["avg_bikes"], 1),
            "avg_docks": round(r["avg_docks"], 1),
            "occupancy_rate": round(occupancy, 1),
            "sample_count": r["sample_count"]
        })
    return hourly_data




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

# def run_pipeline():
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
#
def run_pipeline():
    """Main pipeline execution"""
    logger.info("Starting Historical Data Pipeline")
    
    client, status_collection, history_collection = get_collections()
    db = client[MONGO_DB]
    info_collection = db["station_information"]
    
    try:
        total_status_records = status_collection.count_documents({})
        logger.info(f"Processing {total_status_records} status records")
        
        if total_status_records == 0:
            logger.warning("No status records found. Run station_status_pipeline first.")
            return {"error": "No status data available"}
        
        # Existing calculations
        averages = calculate_station_averages(status_collection)
        peak_hours = calculate_peak_hours(status_collection)
        stored_count = store_historical_results(history_collection, averages, peak_hours)
        
        # --- NEW: Additional KPIs ---
        global_kpis = calculate_global_kpis(status_collection, info_collection)
        top_stations = calculate_top_stations(status_collection, info_collection)
        hourly_occupancy = calculate_occupancy_by_hour(status_collection)
        
        # Store KPIs in a separate collection
        kpi_collection = db["dashboard_kpis"]
        kpi_collection.delete_many({})  # Keep only latest
        kpi_collection.insert_one({
            "type": "global_kpis",
            "data": global_kpis,
            "top_stations": top_stations,
            "hourly_occupancy": hourly_occupancy,
            "calculated_at": datetime.now()
        })
        logger.info(f"Stored dashboard KPIs: {global_kpis}")
        # ---------------------------------
        
        logger.info(f"Historical Pipeline completed. Stored {stored_count} records.")
        return {
            "stations_processed": len(averages), 
            "records_stored": stored_count,
            "kpis": global_kpis
        }
        
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        raise
    finally:
        client.close()

#
def main():
    parser = argparse.ArgumentParser(description="Station History Pipeline")
    parser.add_argument("--no-snapshot", action="store_true", help="Skip snapshot creation")
    args = parser.parse_args()
    
    result = run_pipeline()
    logger.info(f"Pipeline completed: {result}")

if __name__ == "__main__":
    main()
