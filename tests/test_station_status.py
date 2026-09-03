"""Unit tests for station_status_pipeline (no network)."""
from pipelines.station_status_pipeline import transform_all

SAMPLE_PAYLOAD = {
    "lastUpdated": 1779789241,
    "ttl": 60,
    "data": {
        "stations": [
            {
                "station_id": 213688169,
                "num_bikes_available": 7,
                "num_docks_available": 28,
                "is_installed": 1,
                "is_renting": 1,
                "is_returning": 1,
                "last_reported": 1779789200,
            },
            {
                "station_id": 213688170,
                "num_bikes_available": 0,
                "num_docks_available": 20,
                "is_installed": 1,
                "is_renting": 1,
                "is_returning": 1,
                "last_reported": 1779789200,
            },
        ]
    },
}


def test_transform_all_sample():
    docs = transform_all(SAMPLE_PAYLOAD)

    assert len(docs) == 2
    assert docs[0]["station_id"] == 213688169
    assert docs[0]["num_bikes_available"] == 7
    assert docs[0]["num_docks_available"] == 28
    assert docs[0]["occupancy_rate"] == round(7 / 35, 4)
    assert docs[1]["occupancy_rate"] == 0.0
    assert docs[0]["source"] == "velib_metropole"
