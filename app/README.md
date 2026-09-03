# Vélib' GBFS Demo App

Web app for the Big Data school project: **login required**, nearby stations, live bike availability from **MongoDB**, nearby users, and chat.

## Features

- **Login / création de compte** (stockage MongoDB)
- Map (OpenStreetMap + Leaflet) with color-coded stations
- Live data from `gbfs.station_information` + `gbfs.station_status`
- Auto-refresh every 30 seconds
- Share GPS position → see nearby users (WebSocket)
- Contact nearby users via simple chat

## Prerequisites

- MongoDB running with pipeline data (`docker compose up -d` in the main project)
- Python 3.9+

## Run

See **[GUIDE_EQUIPE.md](GUIDE_EQUIPE.md)** for a full team setup guide (French).

Quick start (Windows):

```powershell
cd app
.\run.ps1
```

Or manually:

```powershell
cd app
python -m pip install -r requirements.txt
$env:MONGO_URI = "mongodb://localhost:27017"
python -m uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000**

## Demo for professor

1. Start MongoDB + Airflow pipelines (station info + status)
2. Start this app on port 8000
3. **Créer un compte** ou se connecter (2 onglets = 2 comptes différents)
4. Allow GPS (or use Paris default)
5. Show stations on map with bike counts
6. Show nearby users and send a message between tabs

## Auth

| Endpoint | Description |
|----------|-------------|
| `POST /api/auth/register` | Créer un compte (`username`, `password`, `display_name` optionnel) |
| `POST /api/auth/login` | Connexion → retourne un `token` |
| `GET /api/auth/me` | Vérifier la session (header `Authorization: Bearer <token>`) |
| `POST /api/auth/logout` | Déconnexion |

Comptes stockés dans MongoDB : collections `app_users` et `app_sessions`.

## API (protégée — login requis)

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | MongoDB connection check (public) |
| `GET /api/stations?lat=&lon=&radius_km=3` | Nearby stations with availability |
| `WS /ws?token=<token>` | User presence + chat |
