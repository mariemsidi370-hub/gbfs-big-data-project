"""
GBFS Vélib' Demo App — FastAPI backend.

Auth (register/login) + MongoDB station data + WebSocket chat.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from pymongo import ASCENDING, MongoClient

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "gbfs")
NEARBY_RADIUS_KM = float(os.getenv("NEARBY_RADIUS_KM", "3"))
USER_RADIUS_KM = float(os.getenv("USER_RADIUS_KM", "2"))
SESSION_DAYS = int(os.getenv("SESSION_DAYS", "7"))
USERS_COLLECTION = "app_users"
SESSIONS_COLLECTION = "app_sessions"
BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="Vélib' GBFS Demo App", version="1.1.0")
active_users: Dict[str, dict] = {}


class RegisterBody(BaseModel):
    username: str = Field(min_length=3, max_length=30)
    password: str = Field(min_length=6, max_length=100)
    display_name: Optional[str] = Field(default=None, max_length=30)


class LoginBody(BaseModel):
    username: str
    password: str


def get_db():
    return MongoClient(MONGO_URI)[MONGO_DB]


def ensure_indexes():
    db = get_db()
    db[USERS_COLLECTION].create_index("username", unique=True)
    db[SESSIONS_COLLECTION].create_index("token", unique=True)
    db[SESSIONS_COLLECTION].create_index("expires_at", expireAfterSeconds=0)


@app.on_event("startup")
def on_startup():
    try:
        ensure_indexes()
    except Exception:
        pass


def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


def create_session(user_id, username: str, display_name: str) -> str:
    db = get_db()
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    db[SESSIONS_COLLECTION].insert_one(
        {
            "token": token,
            "user_id": user_id,
            "username": username,
            "display_name": display_name,
            "expires_at": expires_at,
            "created_at": datetime.now(timezone.utc),
        }
    )
    return token


def get_user_by_token(token: str) -> Optional[dict]:
    if not token:
        return None
    db = get_db()
    session = db[SESSIONS_COLLECTION].find_one({"token": token})
    if not session:
        return None
    expires = session.get("expires_at")
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires and expires < datetime.now(timezone.utc):
        db[SESSIONS_COLLECTION].delete_one({"token": token})
        return None
    return {
        "user_id": str(session["user_id"]),
        "username": session["username"],
        "display_name": session.get("display_name") or session["username"],
    }


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Connexion requise")
    user = get_user_by_token(authorization[7:].strip())
    if not user:
        raise HTTPException(status_code=401, detail="Session expirée — reconnectez-vous")
    return user


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def load_stations_with_status() -> List[dict]:
    db = get_db()
    status_by_id = {s["station_id"]: s for s in db.station_status.find()}
    stations = []
    for info in db.station_information.find():
        if info.get("lat") is None or info.get("lon") is None:
            continue
        sid = info["station_id"]
        status = status_by_id.get(sid, {})
        stations.append(
            {
                "station_id": sid,
                "name": info.get("name"),
                "lat": info["lat"],
                "lon": info["lon"],
                "capacity": info.get("capacity"),
                "num_bikes_available": status.get("num_bikes_available"),
                "num_docks_available": status.get("num_docks_available"),
                "occupancy_rate": status.get("occupancy_rate"),
                "is_renting": status.get("is_renting"),
                "is_returning": status.get("is_returning"),
                "status_updated": status.get("ingested_at"),
            }
        )
    return stations


def list_nearby_users(lat: float, lon: float, exclude_id: Optional[str] = None) -> List[dict]:
    users = []
    for uid, u in active_users.items():
        if uid == exclude_id or u.get("lat") is None:
            continue
        d = haversine_km(lat, lon, u["lat"], u["lon"])
        if d <= USER_RADIUS_KM:
            users.append(
                {
                    "id": uid,
                    "name": u["name"],
                    "username": u.get("username"),
                    "lat": u["lat"],
                    "lon": u["lon"],
                    "distance_km": round(d, 2),
                }
            )
    users.sort(key=lambda x: x["distance_km"])
    return users


async def broadcast_users():
    for uid, user in list(active_users.items()):
        ws = user.get("ws")
        lat, lon = user.get("lat"), user.get("lon")
        if ws is None or lat is None or lon is None:
            continue
        payload = {
            "type": "users",
            "users": list_nearby_users(lat, lon, exclude_id=uid),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            await ws.send_json(payload)
        except Exception:
            pass


@app.post("/api/auth/register")
def register(body: RegisterBody):
    username = body.username.strip().lower()
    if not username.replace("_", "").isalnum():
        raise HTTPException(status_code=400, detail="Identifiant: lettres, chiffres et _ uniquement")

    db = get_db()
    if db[USERS_COLLECTION].find_one({"username": username}):
        raise HTTPException(status_code=400, detail="Ce compte existe déjà")

    salt = secrets.token_hex(16)
    display_name = (body.display_name or username).strip()[:30]
    user_doc = {
        "username": username,
        "display_name": display_name,
        "password_hash": hash_password(body.password, salt),
        "salt": salt,
        "created_at": datetime.now(timezone.utc),
    }
    result = db[USERS_COLLECTION].insert_one(user_doc)
    token = create_session(result.inserted_id, username, display_name)
    return {
        "token": token,
        "user": {"username": username, "display_name": display_name},
    }


@app.post("/api/auth/login")
def login(body: LoginBody):
    username = body.username.strip().lower()
    db = get_db()
    user = db[USERS_COLLECTION].find_one({"username": username})
    if not user:
        raise HTTPException(status_code=401, detail="Identifiant ou mot de passe incorrect")

    expected = hash_password(body.password, user["salt"])
    if expected != user["password_hash"]:
        raise HTTPException(status_code=401, detail="Identifiant ou mot de passe incorrect")

    display_name = user.get("display_name") or username
    token = create_session(user["_id"], username, display_name)
    return {
        "token": token,
        "user": {"username": username, "display_name": display_name},
    }


@app.get("/api/auth/me")
def me(user: dict = Depends(get_current_user)):
    return {"user": user}


@app.post("/api/auth/logout")
def logout(authorization: Optional[str] = Header(None)):
    if authorization and authorization.startswith("Bearer "):
        get_db()[SESSIONS_COLLECTION].delete_one({"token": authorization[7:].strip()})
    return {"ok": True}


@app.get("/api/health")
def health():
    try:
        db = get_db()
        count = db.station_status.count_documents({})
        return {"ok": True, "station_status_count": count, "mongo": MONGO_URI}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


@app.get("/api/stations")
def stations(
    lat: Optional[float] = Query(None),
    lon: Optional[float] = Query(None),
    radius_km: float = Query(NEARBY_RADIUS_KM, ge=0.1, le=50),
    user: dict = Depends(get_current_user),
):
    all_stations = load_stations_with_status()

    if lat is not None and lon is not None:
        with_distance = []
        for s in all_stations:
            entry = dict(s)
            entry["distance_km"] = round(haversine_km(lat, lon, s["lat"], s["lon"]), 2)
            with_distance.append(entry)
        nearby = [s for s in with_distance if s["distance_km"] <= radius_km]
        nearby.sort(key=lambda x: x["distance_km"])
        return {
            "count": len(with_distance),
            "nearby_count": len(nearby),
            "stations": with_distance,
            "nearby": nearby,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    return {
        "count": len(all_stations),
        "nearby_count": 0,
        "stations": all_stations,
        "nearby": [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, token: Optional[str] = None):
    user = get_user_by_token(token or "")
    if not user:
        await ws.close(code=4401)
        return

    await ws.accept()
    client_id = str(uuid.uuid4())[:8]
    active_users[client_id] = {
        "name": user["display_name"],
        "username": user["username"],
        "lat": None,
        "lon": None,
        "ws": ws,
    }

    try:
        await ws.send_json(
            {
                "type": "welcome",
                "client_id": client_id,
                "user": user,
                "message": "Connecté — partagez votre position pour voir les utilisateurs proches.",
            }
        )

        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            msg_type = data.get("type")

            if msg_type == "presence":
                active_users[client_id]["lat"] = float(data["lat"])
                active_users[client_id]["lon"] = float(data["lon"])
                await broadcast_users()

            elif msg_type == "message":
                target_id = data.get("to")
                text = (data.get("text") or "").strip()[:500]
                sender = active_users[client_id]["name"]
                if not text:
                    continue
                if target_id not in active_users:
                    await ws.send_json(
                        {
                            "type": "message_error",
                            "text": "Utilisateur déconnecté — rouvrez la conversation.",
                        }
                    )
                    continue
                target_ws = active_users[target_id].get("ws")
                if target_ws:
                    await target_ws.send_json(
                        {
                            "type": "message",
                            "from_id": client_id,
                            "from_name": sender,
                            "text": text,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                    await ws.send_json({"type": "message_sent", "to_id": target_id, "text": text})

    except WebSocketDisconnect:
        pass
    finally:
        active_users.pop(client_id, None)
        await broadcast_users()


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")
