-- Station Information — exemples de requêtes Trino sur MongoDB
-- Prérequis : collection gbfs.station_information alimentée par la pipeline
-- Connexion Trino : catalog mongodb, schema = nom de la base (gbfs)

-- 1) Aperçu des stations
SELECT
    station_id,
    station_code,
    name,
    lat,
    lon,
    capacity,
    ingested_at
FROM mongodb.gbfs.station_information
ORDER BY name
LIMIT 20;

-- 2) Stations avec la plus grande capacité
SELECT
    name,
    station_code,
    capacity,
    lat,
    lon
FROM mongodb.gbfs.station_information
WHERE capacity IS NOT NULL
ORDER BY capacity DESC
LIMIT 15;

-- 3) Stations acceptant la carte bancaire (enrichissement pour dashboards)
SELECT
    name,
    station_code,
    capacity,
    rental_methods
FROM mongodb.gbfs.station_information
WHERE contains(rental_methods, 'CREDITCARD')
ORDER BY name;

-- 4) Jointure future avec station_status (quand l'autre pipeline sera prête)
-- SELECT
--     i.name,
--     i.capacity,
--     s.num_bikes_available,
--     s.num_docks_available,
--     CAST(s.num_bikes_available AS DOUBLE) / i.capacity AS occupancy_rate
-- FROM mongodb.gbfs.station_information i
-- JOIN mongodb.gbfs.station_status s ON i.station_id = s.station_id;
