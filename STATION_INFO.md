# Station Info Pipeline — Guide complet (Phase 2 + 3)

## Phase 2 — Pipeline manuel (Python)

Dans cette phase, nous exécutons le pipeline de bout en bout sans orchestrateur. Le script Python (`python -m pipelines.station_info_pipeline`) récupère les métadonnées des stations Vélib' via l'API GBFS (`station_information.json`) : nom, coordonnées GPS, capacité, code station. Les étapes sont **fetch** (téléchargement JSON), **transform** (normalisation), **load** (upsert MongoDB + snapshot). Résultat : **1512 stations** dans `gbfs.station_information`.

```powershell
pip install -r pipelines/requirements.txt
$env:MONGO_URI = "mongodb://localhost:27017"
python -m pipelines.station_info_pipeline
```

## Phase 3 — Automatisation (Airflow)

Le même pipeline est automatisé via le DAG `station_info_pipeline` (3 tâches : fetch → transform → load), planifié **toutes les 6 heures**. Infrastructure : Docker Compose (MongoDB + PostgreSQL + Airflow). Interface : http://localhost:8080 (`admin` / `admin`).

```powershell
docker compose up -d
```

Puis activer le DAG et cliquer **Trigger DAG**. Vérification :

```powershell
docker exec gbfs_mongodb mongosh --quiet --eval "db.getSiblingDB('gbfs').station_information.countDocuments()"
```

## Fichiers du projet (Station Info)

| Fichier | Rôle |
|---------|------|
| `pipelines/station_info_pipeline.py` | Tout le code Python (fetch, transform, load) |
| `airflow/dags/station_info_dag.py` | Orchestration Airflow |
| `docker-compose.yml` | MongoDB, Airflow, Trino, Superset |
| `tests/test_station_info.py` | Tests unitaires |
| `gitignore` | **Renommer en `.gitignore`** sur GitHub après upload |

## Collections MongoDB

- `gbfs.station_information` — une ligne par station (jointures Phase 4)
- `gbfs.station_information_snapshots` — snapshot à chaque exécution
