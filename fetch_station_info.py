import requests
import json
from pymongo import MongoClient
from datetime import datetime

# GBFS Station Information API (Paris/Velib)
URL = "https://velib-metropole-opendata.smovengo.cloud/opendata/Velib_Metropole/station_information.json"

# MongoDB connection
MONGO_HOST = "localhost"
MONGO_PORT = 27017
MONGO_DB = "gbfs"
MONGO_COLLECTION = "station_info"

def fetch_station_info():
    """Fetch station information from GBFS API"""
    try:
        print(f"[1] Fetching data from API...")
        response = requests.get(URL)
        response.raise_for_status()
        data = response.json()
        
        # Extract stations from response
        stations = data.get("data", {}).get("stations", [])
        
        print(f"[SUCCESS] Fetched {len(stations)} stations")
        return stations
    except Exception as e:
        print(f"[ERROR] Fetching data: {e}")
        return []

def store_in_mongodb(stations):
    """Store station information in MongoDB"""
    try:
        print(f"[2] Connecting to MongoDB...")
        client = MongoClient(MONGO_HOST, MONGO_PORT)
        db = client[MONGO_DB]
        collection = db[MONGO_COLLECTION]
        
        # Add timestamp to each station
        for station in stations:
            station["last_updated"] = datetime.now()
        
        # Clear existing data and insert new (stations rarely change)
        collection.delete_many({})
        result = collection.insert_many(stations)
        
        print(f"[SUCCESS] Stored {len(result.inserted_ids)} stations in MongoDB")
        print(f"[INFO] Database: {MONGO_DB}")
        print(f"[INFO] Collection: {MONGO_COLLECTION}")
        client.close()
    except Exception as e:
        print(f"[ERROR] Storing in MongoDB: {e}")

def show_sample(stations):
    """Display a sample station to verify data"""
    if stations:
        sample = stations[0]
        print("\n" + "="*50)
        print("SAMPLE STATION DATA:")
        print("="*50)
        print(f"Station ID: {sample.get('station_id', 'N/A')}")
        print(f"Name: {sample.get('name', 'N/A')}")
        print(f"Address: {sample.get('address', 'N/A')}")
        print(f"Latitude: {sample.get('lat', 'N/A')}")
        print(f"Longitude: {sample.get('lon', 'N/A')}")
        print(f"Capacity: {sample.get('capacity', 'N/A')}")
        print("="*50)

def main():
    print("\n" + "="*50)
    print("STATION INFO PIPELINE")
    print("="*50)
    
    stations = fetch_station_info()
    
    if stations:
        store_in_mongodb(stations)
        show_sample(stations)
        print("\n[SUCCESS] Station Info Pipeline Complete!")
    else:
        print("\n[FAILED] Pipeline failed - no stations fetched")

if __name__ == "__main__":
    main()