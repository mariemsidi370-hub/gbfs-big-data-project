\# GBFS Big Data Project



\## Overview

This project implements a complete Big Data pipeline for processing real-time bike station data from the Velib Metropole GBFS API.



\## Technologies Used



| Component | Technology | Purpose |

|-----------|------------|---------|

| Data Source | GBFS API (Velib Metropole) | Bike station data |

| Data Ingestion | Python + requests | Fetch API data |

| Storage | MongoDB | Document database |

| SQL Engine | Trino | Query MongoDB with SQL |

| Orchestration | Apache Airflow | Schedule and monitor pipelines |

| Visualization | Apache Superset | Dashboards and charts |

| Containerization | Docker | Run all services |



\## Data Collections



| Collection | Records | Description |

|------------|---------|-------------|

| station\_info | 1,512 | Station names, coordinates, capacity |

| station\_status | 1,512+ | Live bike availability |

| station\_history | 1,512 | Aggregated trends and averages |



\## Quick Start



\### Prerequisites

\- Docker Desktop

\- Python 3.11+

\- Git



\### Installation



```bash

git clone https://github.com/mariemsidi370-hub/gbfs-big-data-project.git

cd gbfs-big-data-project

docker-compose up -d







