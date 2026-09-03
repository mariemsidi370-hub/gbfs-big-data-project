-- Station Status : exemples Trino sur MongoDB

-- 1) Stations avec le plus de vélos disponibles
SELECT station_id, num_bikes_available, num_docks_available, occupancy_rate, ingested_at
FROM mongodb.gbfs.station_status
ORDER BY num_bikes_available DESC
LIMIT 20;

-- 2) Stations vides (aucun vélo)
SELECT station_id, num_docks_available, occupancy_rate
FROM mongodb.gbfs.station_status
WHERE num_bikes_available = 0
ORDER BY num_docks_available DESC;

-- 3) Jointure avec station_information (occupation vs capacité)
SELECT
    i.name,
    i.capacity,
    s.num_bikes_available,
    s.num_docks_available,
    s.occupancy_rate,
    CAST(s.num_bikes_available AS DOUBLE) / i.capacity AS occupancy_vs_capacity
FROM mongodb.gbfs.station_information i
JOIN mongodb.gbfs.station_status s ON i.station_id = s.station_id
WHERE i.capacity IS NOT NULL AND i.capacity > 0
ORDER BY occupancy_vs_capacity DESC
LIMIT 20;
