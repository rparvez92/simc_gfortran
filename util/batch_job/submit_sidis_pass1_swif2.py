#!/usr/bin/env python3
"""Preflight, preview, or submit Pass-1 SIMC jobs to SWIF2."""

from __future__ import annotations

import argparse
import csv
import os
import shlex
import subprocess
import sys
from collections import Counter
from pathlib import Path


REACTIONS = {"sidis": 100_000, "rho": 10_000, "delta": 10_000, "exclusive": 10_000}
SUBMIT_REACTIONS = ("sidis", "delta", "exclusive")
REQUIRED = {"job_id", "reaction", "charge", "ngen", "input_file", "validation_status"}


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simc-dir", required=True, type=Path)
    parser.add_argument("--job-list", required=True, type=Path)
    parser.add_argument("--workflow", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight-only", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--pilot", action="store_true", help="submit one job per reaction")
    mode.add_argument("--submit", action="store_true", help="submit every manifest job")
    parser.add_argument("--partition", default="production")
    parser.add_argument("--cores", default="1")
    parser.add_argument("--ram", default="3000MB")
    parser.add_argument("--time", default="2h")
    parser.add_argument("--disk", default="5GB")
    parser.add_argument(
        "--reaction",
        action="append",
        choices=tuple(REACTIONS),
        help=(
            "reaction to submit; repeat for multiple reactions "
            "(default: sidis, delta, exclusive)"
        ),
    )
    return parser.parse_args()


def load_jobs(path: Path, simc_dir: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        missing = REQUIRED - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"job list is missing columns: {sorted(missing)}")
        jobs = list(reader)
    if not jobs:
        raise ValueError("job list is empty")

    seen: set[str] = set()
    for row in jobs:
        job_id = row["job_id"]
        if not job_id or job_id in seen:
            raise ValueError(f"empty or duplicate job_id: {job_id!r}")
        seen.add(job_id)
        reaction = row["reaction"]
        if reaction not in REACTIONS:
            raise ValueError(f"invalid reaction for {job_id}: {reaction!r}")
        if row["validation_status"] != "VALID":
            raise ValueError(f"job is not VALID: {job_id}")
        if int(row["ngen"]) != REACTIONS[reaction]:
            raise ValueError(f"unexpected ngen for {job_id}: {row['ngen']}")
        if reaction == "exclusive" and row["charge"] != "pip":
            raise ValueError(f"exclusive job is not pip: {job_id}")
        relative = Path(row["input_file"])
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe input path for {job_id}: {relative}")
        if not (simc_dir / relative).is_file():
            raise ValueError(f"missing input for {job_id}: {simc_dir / relative}")
    return jobs


def command(args: argparse.Namespace, worker: Path, job_id: str) -> list[str]:
    return [
        "swif2", "add-job", "-workflow", args.workflow,
        "-name", job_id, "-partition", args.partition,
        "-cores", args.cores, "-ram", args.ram,
        "-time", args.time, "-disk", args.disk,
        "/bin/bash", str(worker), str(args.simc_dir),
        str(args.job_list), job_id,
    ]


def main() -> int:
    args = arguments()
    args.simc_dir = args.simc_dir.expanduser().resolve()
    args.job_list = args.job_list.expanduser().resolve()
    batch_dir = args.simc_dir / "util" / "batch_job"
    worker = batch_dir / "run_sidis_pass1_swif_job.sh"
    one_job = batch_dir / "run_sidis_pass1_job.py"
    for path in (worker, one_job, args.job_list):
        if not path.is_file():
            raise ValueError(f"required file is missing: {path}")
    for executable in (
        args.simc_dir / "simc",
        args.simc_dir / "run_simc_tree",
        args.simc_dir / "util" / "root_tree" / "make_root_tree",
    ):
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError(f"required executable is missing: {executable}")

    jobs = load_jobs(args.job_list, args.simc_dir)
    counts = Counter(row["reaction"] for row in jobs)
    print(
        f"Validated {len(jobs)} jobs "
        f"(sidis={counts['sidis']}, rho={counts['rho']}, "
        f"delta={counts['delta']}, exclusive={counts['exclusive']})"
    )
    selected_reactions = tuple(dict.fromkeys(args.reaction or SUBMIT_REACTIONS))
    jobs = [row for row in jobs if row["reaction"] in selected_reactions]
    selected_counts = Counter(row["reaction"] for row in jobs)
    selected_summary = ", ".join(
        f"{reaction}={selected_counts[reaction]}" for reaction in selected_reactions
    )
    print(f"Current submission set: {len(jobs)} jobs ({selected_summary})")
    if args.preflight_only:
        return 0

    if args.pilot:
        selected: dict[str, dict[str, str]] = {}
        for row in jobs:
            selected.setdefault(row["reaction"], row)
        jobs = [selected[name] for name in selected_reactions]
        print("Pilot jobs: " + ", ".join(row["job_id"] for row in jobs))

    create = ["swif2", "create", "-workflow", args.workflow]
    run = ["swif2", "run", "-workflow", args.workflow]
    status = ["swif2", "status", "-workflow", args.workflow]
    commands = [command(args, worker, row["job_id"]) for row in jobs]
    if args.dry_run:
        print(shlex.join(create))
        for item in commands:
            print(shlex.join(item))
        print(shlex.join(run))
        print(shlex.join(status))
        print(f"Dry run: prepared {len(commands)} add-job commands")
        return 0

    subprocess.run(create, check=True)
    for index, item in enumerate(commands, start=1):
        subprocess.run(item, check=True)
        print(f"[{index}/{len(commands)}] added {jobs[index - 1]['job_id']}")
    subprocess.run(run, check=True)
    subprocess.run(status, check=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(2)
