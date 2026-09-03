# Guide équipe — lancer l'app Vélib' Demo

Ce fichier explique comment **chaque membre de l'équipe** peut lancer l'application web (`app/`) en local.

---

## Ce dont vous avez besoin

| Outil | Version | Vérifier |
|-------|---------|----------|
| **Docker Desktop** | récent | doit être **démarré** (icône verte) |
| **Python** | 3.9+ | `python --version` |
| **Git** | — | clone du repo projet |

---

## Étape 1 — Démarrer MongoDB (obligatoire)

L'app lit les stations dans MongoDB. Sans MongoDB, la carte reste vide.

```powershell
cd "chemin\vers\gbfs-big-data-project-team"
docker compose up -d mongodb
```

Vérifier que le conteneur tourne :

```powershell
docker ps
```

Vous devez voir `gbfs_mongodb` sur le port **27017**.

Si le conteneur existe déjà mais est arrêté :

```powershell
docker start gbfs_mongodb
```

---

## Étape 2 — Avoir des données dans MongoDB

Les collections utilisées par l'app :

- `gbfs.station_information` — infos stations (nom, GPS, capacité)
- `gbfs.station_status` — vélos / docks en temps réel

**Option A — Pipelines Airflow déjà lancés (recommandé)**

1. Démarrer la stack complète si besoin : `docker compose up -d`
2. Ouvrir Airflow : http://localhost:8080 (admin / admin)
3. Activer et lancer les DAGs :
   - `station_info_pipeline`
   - `station_status_pipeline`
4. Attendre que les 3 tâches de chaque DAG soient **vertes**

**Option B — Vérifier rapidement**

```powershell
docker exec -it gbfs_mongodb mongosh --eval "db.getSiblingDB('gbfs').station_status.countDocuments()"
```

Résultat attendu : un nombre > 0 (ex. **1516**).

---

## Étape 3 — Installer et lancer l'app

```powershell
cd "chemin\vers\app"
python -m pip install -r requirements.txt
$env:MONGO_URI = "mongodb://localhost:27017"
python -m uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

Ouvrir dans le navigateur : **http://localhost:8000**

### Script rapide (Windows)

Depuis le dossier `app/` :

```powershell
.\run.ps1
```

---

## Étape 4 — Utiliser l'app

1. **Créer un compte** ou se connecter (login obligatoire)
2. Cliquer sur **« Utiliser ma position »**
   - Si vous refusez le GPS → position par défaut = **centre Paris** (mieux pour voir les stations Vélib')
   - Si vous êtes loin de Paris (ex. Maroc) → la carte zoome sur Paris ; la liste montre les stations les plus proches
3. La carte affiche ~**1516 stations** ; la sidebar liste celles **à moins de 3 km**
4. Le statut en haut doit afficher : `MongoDB · X proches / 1516 stations`

---

## Tester le chat entre 2 utilisateurs

| Méthode | Fonctionne ? |
|---------|--------------|
| Chrome + Firefox | ✅ |
| Fenêtre normale + navigation privée | ✅ |
| 2 onglets du même navigateur | ❌ (même session) |

**Procédure :**

1. Compte **user1** dans Chrome, compte **user2** dans Firefox (ou fenêtre privée)
2. **Utiliser ma position** dans les deux fenêtres (même lieu = < 2 km)
3. Vérifier **« Utilisateurs proches »** — l'autre compte doit apparaître
4. **Contacter** → envoyer un message
5. L'autre fenêtre reçoit le message et ouvre le chat automatiquement

---

## Dépannage

### « MongoDB hors ligne »

- Docker Desktop est-il démarré ?
- `docker start gbfs_mongodb`
- Vérifier : http://localhost:8000/api/health → `"ok": true`

### Port 8000 déjà utilisé

```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | Select OwningProcess
Stop-Process -Id <PID> -Force
```

Puis relancer uvicorn.

### Aucune station affichée

- MongoDB vide → lancer les pipelines Airflow (étape 2)
- Trop loin de Paris → refuser le GPS ou accepter la position Paris par défaut
- Recharger la page : **Ctrl+F5**

### Message chat non reçu

- Les 2 comptes doivent être visibles dans « Utilisateurs proches »
- Statut = **Connecté** (WebSocket actif)
- Utiliser **2 navigateurs différents**, pas 2 onglets Chrome
- Recharger les 2 pages après une déconnexion, puis **Contacter** à nouveau

### Session / login

- Comptes stockés dans MongoDB : `gbfs.app_users`, `gbfs.app_sessions`
- Déconnexion via le bouton en haut à droite

---

## Structure du dossier `app/`

```
app/
├── server.py           # Backend FastAPI (auth + API + WebSocket)
├── requirements.txt    # Dépendances Python
├── run.ps1             # Lancement rapide Windows
├── GUIDE_EQUIPE.md     # Ce fichier
├── README.md           # Doc technique
└── static/
    ├── index.html
    ├── css/style.css
    └── js/app.js
```

---

## URLs utiles

| Service | URL |
|---------|-----|
| App web | http://localhost:8000 |
| Health check | http://localhost:8000/api/health |
| Airflow | http://localhost:8080 |
| MongoDB | localhost:27017 |

---

## Contact / questions

En cas de blocage, vérifier dans l'ordre : **Docker → MongoDB → données → app → navigateur**.

Partager une capture du statut en haut de l'app + la sortie de `/api/health` aide à diagnostiquer rapidement.
