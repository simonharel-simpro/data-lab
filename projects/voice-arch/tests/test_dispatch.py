from voice_arch.dispatch import http_url, metadata_json


def test_http_url_maps_ws_schemes_to_http_schemes() -> None:
    assert http_url("ws://127.0.0.1:7880") == "http://127.0.0.1:7880"
    assert http_url("wss://lk.example.com") == "https://lk.example.com"


def test_metadata_round_trips_through_the_workers_parser() -> None:
    from voice_arch.arch import Arch
    from voice_arch.worker_logic import parse_metadata

    run_id = "abc123"

    assert parse_metadata(metadata_json("b", run_id)) == (Arch.B, run_id)
    assert parse_metadata(metadata_json("c")) == (Arch.C, "manual")
