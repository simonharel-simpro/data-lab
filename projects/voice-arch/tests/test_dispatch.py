from voice_arch.dispatch import http_url


def test_http_url_maps_ws_schemes_to_http_schemes() -> None:
    assert http_url("ws://127.0.0.1:7880") == "http://127.0.0.1:7880"
    assert http_url("wss://lk.example.com") == "https://lk.example.com"
