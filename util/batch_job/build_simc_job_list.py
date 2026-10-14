#!/usr/bin/env python3
"""Build a deterministic SIMC job manifest from the R-SIDIS bigtable.

The run-level bigtable determines which pass/charge/target/setting
combinations were observed. Canonical kinematics come from the nominal
settings catalog so that harmless run-to-run setting variations do not
create additional Monte Carlo jobs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import os
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Mapping, Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
SOURCE_DIR = SCRIPT_DIR / "source_files"
DEFAULT_BIGTABLE = SOURCE_DIR / "rp_rsidis_bigtable_pass1_sidis.csv"
DEFAULT_NOMINAL_SETTINGS = SOURCE_DIR / "nominal_kinematics_sidis_settings.csv"
DEFAULT_OUTPUT = SCRIPT_DIR / "simc_job_list_pass1.csv"

REACTIONS = ("sidis", "rho", "delta", "exclusive")
CHARGES = ("pip", "pim")
TARGETS = ("LH2", "LD2")
PASSES = ("pass3", "pass4", "pass5")
PHASES = ("phase1", "phase2")

EVENT_COUNTS = {
    "sidis": 100_000,
    "rho": 10_000,
    "delta": 10_000,
    "exclusive": 10_000,
}

# A pass number alone does not distinguish the two 8.58 GeV periods. The
# phase and canonical beam energy together provide an unambiguous mapping.
PASS_BY_PHASE_AND_BEAM = {
    ("phase1", Decimal("8.5831")): "pass4",
    ("phase1", Decimal("10.6716")): "pass5",
    ("phase2", Decimal("6.4724")): "pass3",
    ("phase2", Decimal("8.5814")): "pass4",
    ("phase2", Decimal("10.6759")): "pass5",
}

BIGTABLE_REQUIRED = {
    "run",
    "ebeam",
    "target",
    "run_type",
    "setting_id",
}
NOMINAL_REQUIRED = {
    "setting_id",
    "phase",
    "x",
    "Q2",
    "z",
    "theta_pq",
    "ebeam",
    "hms_p_magnitude",
    "hms_th",
    "shms_p_magnitude",
    "shms_th",
}

KINEMATIC_COLUMNS = (
    "x",
    "Q2",
    "z",
    "theta_pq",
    "ebeam",
    "hms_p_magnitude",
    "hms_th",
    "shms_p_magnitude",
    "shms_th",
)

OUTPUT_COLUMNS = (
    "job_id",
    "phase",
    "pass",
    "reaction",
    "simc_reaction",
    "charge",
    "target",
    "setting_id",
    "ngen",
    "random_seed",
    *KINEMATIC_COLUMNS,
    "source_run_count",
    "source_runs",
    "input_file",
    "simc_root_file",
    "recon_root_file",
    "source_bigtable",
    "source_bigtable_sha256",
    "source_nominal_settings",
    "source_nominal_settings_sha256",
    "validation_status",
    "validation_message",
)


@dataclass(frozen=True)
class ObservedKey:
    phase: str
    pass_name: str
    charge: str
    target: str
    setting_id: str


def read_csv(path: Path, required: set[str]) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise ValueError("CSV has no header")
            missing = sorted(required.difference(reader.fieldnames))
            if missing:
                raise ValueError(f"missing required columns: {', '.join(missing)}")
            rows = list(reader)
    except OSError as error:
        raise ValueError(f"cannot read {path}: {error}") from error
    except csv.Error as error:
        raise ValueError(f"cannot parse {path}: {error}") from error
    if not rows:
        raise ValueError(f"{path} contains no data rows")
    return rows


def decimal_value(raw: str, label: str) -> Decimal:
    try:
        value = Decimal(raw.strip())
    except (AttributeError, InvalidOperation) as error:
        raise ValueError(f"invalid decimal for {label}: {raw!r}") from error
    if not value.is_finite():
        raise ValueError(f"non-finite decimal for {label}: {raw!r}")
    return value


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_nominal_settings(path: Path) -> dict[str, dict[str, str]]:
    """Load either the 51-row or channel-expanded nominal catalog."""
    rows = read_csv(path, NOMINAL_REQUIRED)
    by_setting: dict[str, dict[str, str]] = {}
    for row_number, row in enumerate(rows, start=2):
        setting_id = row["setting_id"].strip()
        phase = row["phase"].strip()
        if not setting_id:
            raise ValueError(f"{path}:{row_number}: blank setting_id")
        if phase not in PHASES:
            raise ValueError(f"{path}:{row_number}: invalid phase {phase!r}")

        canonical = {name: row[name].strip() for name in KINEMATIC_COLUMNS}
        canonical["phase"] = phase
        for name in KINEMATIC_COLUMNS:
            decimal_value(canonical[name], f"{setting_id}.{name}")

        beam = decimal_value(canonical["ebeam"], f"{setting_id}.ebeam")
        if (phase, beam) not in PASS_BY_PHASE_AND_BEAM:
            raise ValueError(
                f"{path}:{row_number}: no pass mapping for phase={phase}, "
                f"ebeam={canonical['ebeam']}"
            )

        previous = by_setting.get(setting_id)
        if previous is not None and previous != canonical:
            raise ValueError(
                f"{path}:{row_number}: conflicting nominal rows for {setting_id}"
            )
        by_setting[setting_id] = canonical
    return by_setting


def translate_charge(run_type: str, row_number: int, path: Path) -> str:
    value = run_type.strip().upper()
    if value == "PI+SIDIS":
        return "pip"
    if value == "PI-SIDIS":
        return "pim"
    raise ValueError(f"{path}:{row_number}: unsupported run_type {run_type!r}")


def observed_combinations(
    path: Path, nominal: Mapping[str, Mapping[str, str]]
) -> dict[ObservedKey, set[int]]:
    rows = read_csv(path, BIGTABLE_REQUIRED)
    observed: dict[ObservedKey, set[int]] = defaultdict(set)
    for row_number, row in enumerate(rows, start=2):
        target = row["target"].strip()
        if target not in TARGETS:
            continue
        charge = translate_charge(row["run_type"], row_number, path)
        setting_id = row["setting_id"].strip()
        if setting_id not in nominal:
            raise ValueError(
                f"{path}:{row_number}: setting_id {setting_id!r} is absent from "
                "the nominal settings catalog"
            )
        setting = nominal[setting_id]
        phase = setting["phase"]
        nominal_beam = decimal_value(setting["ebeam"], f"{setting_id}.ebeam")
        observed_beam = decimal_value(row["ebeam"], f"bigtable row {row_number}.ebeam")
        if observed_beam != nominal_beam:
            raise ValueError(
                f"{path}:{row_number}: ebeam={observed_beam} disagrees with "
                f"nominal {setting_id} ebeam={nominal_beam}"
            )
        pass_name = PASS_BY_PHASE_AND_BEAM[(phase, nominal_beam)]
        try:
            run = int(row["run"].strip())
        except ValueError as error:
            raise ValueError(f"{path}:{row_number}: invalid run {row['run']!r}") from error
        if run <= 0:
            raise ValueError(f"{path}:{row_number}: run must be positive")
        observed[
            ObservedKey(phase, pass_name, charge, target, setting_id)
        ].add(run)
    if not observed:
        raise ValueError(f"{path} has no eligible LH2/LD2 SIDIS rows")
    return observed


def stable_seed(job_id: str) -> int:
    # Keep the seed positive and within the signed 32-bit integer range.
    return int.from_bytes(hashlib.sha256(job_id.encode()).digest()[:4], "big") % 2_147_483_646 + 1


def selected(value: str, filters: Sequence[str] | None) -> bool:
    return not filters or value in filters


def build_rows(
    observed: Mapping[ObservedKey, set[int]],
    nominal: Mapping[str, Mapping[str, str]],
    bigtable_path: Path,
    nominal_path: Path,
    args: argparse.Namespace,
) -> list[dict[str, str]]:
    bigtable_hash = file_sha256(bigtable_path)
    nominal_hash = file_sha256(nominal_path)
    rows: list[dict[str, str]] = []
    output_names: set[str] = set()

    pass_order = {name: index for index, name in enumerate(PASSES)}
    charge_order = {name: index for index, name in enumerate(CHARGES)}
    target_order = {name: index for index, name in enumerate(TARGETS)}
    reaction_order = {name: index for index, name in enumerate(REACTIONS)}
    keys = sorted(
        observed,
        key=lambda key: (
            pass_order[key.pass_name],
            key.setting_id,
            charge_order[key.charge],
            target_order[key.target],
        ),
    )
    for key in keys:
        if not (
            selected(key.phase, args.phase)
            and selected(key.pass_name, args.pass_filter)
            and selected(key.charge, args.charge)
            and selected(key.target, args.target)
            and selected(key.setting_id, args.setting_id)
        ):
            continue
        for reaction in sorted(REACTIONS, key=reaction_order.__getitem__):
            if not selected(reaction, args.reaction):
                continue
            if reaction == "exclusive" and key.charge != "pip":
                continue

            job_id = (
                f"mc_{reaction}_{key.pass_name}_{key.charge}_"
                f"{key.target}_{key.setting_id}"
            )
            simc_root = f"{job_id}.root"
            recon_root = f"recon_hcana_{job_id}.root"
            if simc_root in output_names:
                raise ValueError(f"duplicate output filename: {simc_root}")
            output_names.add(simc_root)
            setting = nominal[key.setting_id]
            runs = sorted(observed[key])
            row = {
                "job_id": job_id,
                "phase": key.phase,
                "pass": key.pass_name,
                "reaction": reaction,
                "simc_reaction": "excl" if reaction == "exclusive" else reaction,
                "charge": key.charge,
                "target": key.target,
                "setting_id": key.setting_id,
                "ngen": str(EVENT_COUNTS[reaction]),
                "random_seed": str(stable_seed(job_id)),
                "source_run_count": str(len(runs)),
                "source_runs": ";".join(map(str, runs)),
                "input_file": f"infiles/Pass1/coin/{job_id}.inp",
                "simc_root_file": simc_root,
                "recon_root_file": recon_root,
                "source_bigtable": bigtable_path.name,
                "source_bigtable_sha256": bigtable_hash,
                "source_nominal_settings": nominal_path.name,
                "source_nominal_settings_sha256": nominal_hash,
                "validation_status": "VALID",
                "validation_message": "observed combination joined to canonical kinematics",
            }
            row.update({name: setting[name] for name in KINEMATIC_COLUMNS})
            rows.append(row)
    if not rows:
        raise ValueError("filters selected no jobs")
    return rows


def atomic_write_csv(path: Path, rows: Iterable[Mapping[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=OUTPUT_COLUMNS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def append_filter(parser: argparse.ArgumentParser, name: str, choices: Sequence[str]) -> None:
    parser.add_argument(
        f"--{name}",
        action="append",
        choices=choices,
        help=f"include one {name}; repeat to include more than one",
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bigtable", type=Path, default=DEFAULT_BIGTABLE)
    parser.add_argument(
        "--nominal-settings", type=Path, default=DEFAULT_NOMINAL_SETTINGS
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--dry-run", action="store_true", help="validate and summarize without writing"
    )
    append_filter(parser, "phase", PHASES)
    parser.add_argument(
        "--pass",
        dest="pass_filter",
        action="append",
        choices=PASSES,
        help="include one pass; repeat to include more than one",
    )
    append_filter(parser, "reaction", REACTIONS)
    append_filter(parser, "charge", CHARGES)
    append_filter(parser, "target", TARGETS)
    parser.add_argument(
        "--setting-id",
        action="append",
        help="include one setting_id; repeat to include more than one",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        nominal = load_nominal_settings(args.nominal_settings)
        observed = observed_combinations(args.bigtable, nominal)
        rows = build_rows(observed, nominal, args.bigtable, args.nominal_settings, args)
    except ValueError as error:
        raise SystemExit(f"ERROR: {error}") from error

    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row["reaction"]] += 1
    summary = ", ".join(f"{name}={counts[name]}" for name in REACTIONS if counts[name])
    print(f"Validated {len(nominal)} nominal settings and {len(observed)} observed combinations")
    print(f"Prepared {len(rows)} jobs ({summary})")
    if args.dry_run:
        print("Dry run: no output written")
    else:
        atomic_write_csv(args.output, rows)
        print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
