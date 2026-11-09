"""Guards the shared infra's published ports (F-4, D-4).

data-lab must coexist with Demo-RAG (5000/8080/50051) and, being unauthenticated (#2), must only listen on
127.0.0.1. A wrong gRPC mapping gives a split-brain Weaviate: REST on data-lab, gRPC on Demo-RAG.
"""

import json
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSE_FILE = REPO_ROOT / "compose.yaml"

# (service, host ip, published port, target port, protocol)
EXPECTED_PORTS = {
    ("weaviate", "127.0.0.1", "8090", 8080, "tcp"),
    ("weaviate", "127.0.0.1", "50052", 50051, "tcp"),
    ("mlflow", "127.0.0.1", "5050", 5000, "tcp"),
    ("livekit", "127.0.0.1", "7880", 7880, "tcp"),
    ("livekit", "127.0.0.1", "7881", 7881, "tcp"),
    ("livekit", "127.0.0.1", "7882", 7882, "udp"),
}


def _compose_config(*profiles: str) -> dict:
    docker = shutil.which("docker")
    if docker is None:
        raise unittest.SkipTest("docker is not on PATH: cannot render compose.yaml with `docker compose config`")
    # Fixed argv, no shell, absolute binary path: nothing user-controlled reaches the command line.
    profile_args = [arg for profile in profiles for arg in ("--profile", profile)]
    result = subprocess.run(  # noqa: S603  # fixed argv list, no shell
        [docker, "compose", "-f", str(COMPOSE_FILE), *profile_args, "config", "--format", "json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, f"docker compose config failed: {result.stderr}"
    return json.loads(result.stdout)


def test_f_4_compose_maps_distinct_host_ports() -> None:
    config = _compose_config("voice")

    published = set()
    host_ips = []
    for service_name, service in config["services"].items():
        for port in service.get("ports", []):
            if port.get("published") is None:
                continue
            host_ips.append(port.get("host_ip"))
            published.add(
                (service_name, port.get("host_ip"), str(port["published"]), int(port["target"]), port["protocol"])
            )

    assert published == EXPECTED_PORTS
    assert host_ips, "no published port found"
    assert all(ip == "127.0.0.1" for ip in host_ips), host_ips


def test_d_19_default_render_has_no_livekit_service() -> None:
    config = _compose_config()

    assert "livekit" not in config["services"]
    assert set(config["services"]) == {"weaviate", "t2v-transformers", "mlflow"}
