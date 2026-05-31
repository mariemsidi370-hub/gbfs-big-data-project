"""Unit tests for station_info_pipeline (no network)."""
from pipelines.station_info_pipeline import transform_all

SAMPLE_PAYLOAD = {
    "lastUpdatedOther": 1779788753,
    "ttl": 3600,
    "data": {
        "stations": [
            {
                "station_id": 213688169,
                "stationCode": "16107",
                "name": "Benjamin Godard - Victor Hugo",
                "lat": 48.865,
                "lon": 2.287,
                "capacity": 35,
                "rental_methods": ["CREDITCARD", "KEY"],
            },
            {
                "station_id": 213688170,
                "stationCode": "16108",
                "name": "Test Station",
                "lat": 48.87,
                "lon": 2.29,
                "capacity": 20,
                "rental_methods": "CREDITCARD",
            },
        ]
    },
}


def test_transform_all_sample():
    docs = transform_all(SAMPLE_PAYLOAD)

    assert len(docs) == 2
    assert docs[0]["station_id"] == 213688169
    assert docs[0]["station_code"] == "16107"
    assert docs[0]["name"] == "Benjamin Godard - Victor Hugo"
    assert docs[0]["capacity"] == 35
    assert docs[1]["rental_methods"] == ["CREDITCARD"]
    assert docs[0]["source"] == "velib_metropole"
