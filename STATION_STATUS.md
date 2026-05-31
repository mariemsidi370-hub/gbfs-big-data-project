# Station Status Pipeline — Guide (Phase 2 + 3)

## Rôle

Pipeline **temps quasi-réel** : vélos disponibles, docks libres, taux d'occupation.

```
station_status.json (API GBFS)
    → fetch → transform → load → MongoDB
```

| Donnée | Description |
|--------|-------------|
| `num_bikes_available` | Vélos disponibles |
| `num_docks_available` | Places libres |
| `occupancy_rate` | vélos / (vélos + docks) |
| `is_installed` / `is_renting` / `is_returning` | État opérationnel |

## Collections MongoDB

| Collection | Rôle |
|------------|------|
| `gbfs.station_status` | Dernière valeur par `station_id` (live) |
| `gbfs.station_status_snapshots` | Snapshot à chaque run (→ Historical pipeline) |

## Phase 2 — Manuel

```powershell
pip install -r pipelines/requirements.txt
$env:MONGO_URI = "mongodb://localhost:27017"
python -m pipelines.station_status_pipeline
```

Ou : `python fetch_station_status.py`

## Phase 3 — Airflow

DAG : **`station_status_pipeline`** — planifié **toutes les 2 minutes**.

1. `docker compose up -d`
2. http://localhost:8080 → activer le DAG → **Trigger DAG**

## Jointure avec Station Info (Phase 4)

```sql
SELECT i.name, i.capacity, s.num_bikes_available, s.occupancy_rate
FROM mongodb.gbfs.station_information i
JOIN mongodb.gbfs.station_status s ON i.station_id = s.station_id;
```
