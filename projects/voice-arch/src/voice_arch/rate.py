"""`python -m voice_arch.rate --arch a|b|c --rating 1-5 [--notes ...]`: a human's rating of one browser call."""

import argparse
from typing import Final

import mlflow

from datalab.project import Project, load
from datalab.settings import Settings
from datalab.tracking import preflight, tracked_run
from voice_arch.arch import Arch

MIN_RATING: Final = 1
MAX_RATING: Final = 5


def log_rating(project: Project, dl_settings: Settings, arch: str, rating: int, notes: str | None) -> str:
    """One run per rating; it never logs `exact_rate`, so a human run cannot stand in for a sweep (U-6)."""
    if not MIN_RATING <= rating <= MAX_RATING:
        raise ValueError(f"rating must be between {MIN_RATING} and {MAX_RATING}, got {rating}")
    tags = {"source": "human", "arch": Arch(arch).value}
    if notes:
        tags["notes"] = notes
    with tracked_run(project, dl_settings, run_name=f"human-{arch}", sub="human", tags=tags) as run_id:
        mlflow.log_metric("human_rating", float(rating))
    return run_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="voice_arch.rate", description="Log a human rating of one call.")
    parser.add_argument("--arch", choices=[a.value for a in Arch], required=True)
    parser.add_argument("--rating", type=int, required=True, help=f"{MIN_RATING} (robotic) to {MAX_RATING} (natural)")
    parser.add_argument("--notes")
    args = parser.parse_args(argv)
    if not MIN_RATING <= args.rating <= MAX_RATING:
        parser.error(f"--rating must be between {MIN_RATING} and {MAX_RATING}")
    dl, project = Settings(), load()
    preflight(dl.mlflow_tracking_uri)
    print(log_rating(project, dl, args.arch, args.rating, args.notes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
