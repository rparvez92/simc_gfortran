#!/usr/bin/env python3
"""Generate Pass-1 R-SIDIS SIMC inputs from a validated job manifest.

Existing pre-Pass-1 inputs are used as formatting and physics templates.
Only Ngen, beam energy, HMS/SHMS central kinematics, and Egamma_gen_max
are replaced. Reaction, charge, and target flags are validated before and
after rendering.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import tempfile
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping, Sequence


SIMC_DIR = Path(__file__).resolve().parents[2]
SOURCE_DIR = Path(__file__).resolve().parent / "source_files"
DEFAULT_OUTPUT_DIR = SIMC_DIR / "infiles" / "Pass1" / "coin"
DEFAULT_REACTION_FLAGS = SOURCE_DIR / "simc_reaction_flags.csv"

REACTIONS = ("sidis", "rho", "delta", "exclusive")
CHARGES = ("pip", "pim")
TARGETS = ("LH2", "LD2")
EVENT_COUNTS = {
    "sidis": 100_000,
    "rho": 10_000,
    "delta": 10_000,
    "exclusive": 10_000,
}

REQUIRED_COLUMNS = {
    "job_id",
    "phase",
    "pass",
    "reaction",
    "charge",
    "target",
    "setting_id",
    "ngen",
    "ebeam",
    "hms_p_magnitude",
    "hms_th",
    "shms_p_magnitude",
    "shms_th",
    "input_file",
    "validation_status",
}

FLAG_COLUMNS = ("doing_pion", "which_pion", "doing_rho", "doing_semi", "doing_hplus")

TARGET_NUMBERS = {
    "LH2": {"targ%A": Decimal("1"), "targ%Z": Decimal("1")},
    "LD2": {"targ%A": Decimal("2"), "targ%Z": Decimal("1")},
}

TEMPLATE_NAME = re.compile(
    r"^mc_(?P<reaction>sidis|rho|delta|exclusive)_.*_"
    r"(?P<run_type>PIPLUS|PIMINUS)_(?P<target>LH2|LD2)_.*\.inp$"
)


def decimal_value(raw: str, label: str) -> Decimal:
    try:
        value = Decimal(raw.strip())
    except (AttributeError, InvalidOperation) as error:
        raise ValueError(f"invalid decimal for {label}: {raw!r}") from error
    if not value.is_finite():
        raise ValueError(f"non-finite decimal for {label}: {raw!r}")
    return value


def assignment_value(text: str, name: str) -> str:
    pattern = re.compile(
        rf"^\s*{re.escape(name)}\s*=\s*(?P<value>[^;\r\n]+)", re.MULTILINE
    )
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        raise ValueError(f"expected one assignment for {name}, found {len(matches)}")
    return matches[0].group("value").strip()


def replace_assignment(text: str, name: str, value: str) -> str:
    pattern = re.compile(
        rf"^(?P<prefix>\s*{re.escape(name)}\s*=\s*)(?P<value>[^;\r\n]+)",
        re.MULTILINE,
    )
    result, count = pattern.subn(
        lambda match: match.group("prefix") + value, text
    )
    if count != 1:
        raise ValueError(f"expected one assignment for {name}, found {count}")
    return result


def charge_from_run_type(run_type: str) -> str:
    return "pip" if run_type == "PIPLUS" else "pim"


def load_reaction_flags(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    required = {"reaction", "charge", *FLAG_COLUMNS}
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing columns: {sorted(missing)}")
        flags: dict[tuple[str, str], dict[str, str]] = {}
        for row_number, row in enumerate(reader, start=2):
            key = (row["reaction"].strip(), row["charge"].strip())
            if key in flags:
                raise ValueError(
                    f"{path}:{row_number}: duplicate reaction/charge {key}"
                )
            if key[0] not in REACTIONS or key[1] not in CHARGES:
                raise ValueError(
                    f"{path}:{row_number}: invalid reaction/charge {key}"
                )
            values = {name: row[name].strip() for name in FLAG_COLUMNS}
            if any(value not in {"0", "1", "2", "3"} for value in values.values()):
                raise ValueError(f"{path}:{row_number}: invalid flag value")
            flags[key] = values
    needed = {
        (reaction, charge)
        for reaction in REACTIONS
        for charge in CHARGES
        if not (reaction == "exclusive" and charge == "pim")
    }
    missing_keys = needed.difference(flags)
    if missing_keys:
        raise ValueError(
            f"{path}: missing reaction/charge rows: {sorted(missing_keys)}"
        )
    return flags


def discover_templates(template_dir: Path) -> dict[tuple[str, str, str], Path]:
    if not template_dir.is_dir():
        raise ValueError(f"template directory does not exist: {template_dir}")
    candidates: dict[tuple[str, str, str], list[Path]] = {}
    for path in sorted(template_dir.glob("*.inp")):
        match = TEMPLATE_NAME.match(path.name)
        if match is None:
            continue
        key = (
            match.group("reaction"),
            charge_from_run_type(match.group("run_type")),
            match.group("target"),
        )
        candidates.setdefault(key, []).append(path)

    needed = {
        (reaction, charge, target)
        for reaction in REACTIONS
        for charge in CHARGES
        for target in TARGETS
        if not (reaction == "exclusive" and charge == "pim")
    }
    missing = sorted(needed.difference(candidates))
    if missing:
        descriptions = ", ".join("/".join(key) for key in missing)
        raise ValueError(f"missing template combinations: {descriptions}")
    return {key: paths[0] for key, paths in candidates.items() if key in needed}


def validate_template(
    text: str, reaction: str, charge: str, target: str, source: Path,
    reaction_flags: Mapping[tuple[str, str], Mapping[str, str]],
) -> None:
    for name, expected in reaction_flags[(reaction, charge)].items():
        actual = assignment_value(text, name)
        if actual != expected:
            raise ValueError(
                f"{source}: {name}={actual}, expected {expected} for "
                f"{reaction}/{charge}"
            )
    for name, expected in TARGET_NUMBERS[target].items():
        actual = decimal_value(assignment_value(text, name), f"{source}:{name}")
        if actual != expected:
            raise ValueError(
                f"{source}: {name}={actual}, expected {expected} for {target}"
            )


def read_manifest(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise ValueError("manifest has no header")
            missing = sorted(REQUIRED_COLUMNS.difference(reader.fieldnames))
            if missing:
                raise ValueError(f"manifest is missing columns: {', '.join(missing)}")
            rows = list(reader)
    except OSError as error:
        raise ValueError(f"cannot read manifest {path}: {error}") from error
    except csv.Error as error:
        raise ValueError(f"cannot parse manifest {path}: {error}") from error
    if not rows:
        raise ValueError("manifest contains no jobs")
    return rows


def mev(raw_gev: str, label: str) -> str:
    value = decimal_value(raw_gev, label) * Decimal("1000")
    return format(value.quantize(Decimal("0.1")), "f")


def validate_manifest_row(row: Mapping[str, str], row_number: int) -> None:
    reaction = row["reaction"].strip()
    charge = row["charge"].strip()
    target = row["target"].strip()
    if reaction not in REACTIONS:
        raise ValueError(f"manifest row {row_number}: invalid reaction {reaction!r}")
    if charge not in CHARGES:
        raise ValueError(f"manifest row {row_number}: invalid charge {charge!r}")
    if target not in TARGETS:
        raise ValueError(f"manifest row {row_number}: invalid target {target!r}")
    if reaction == "exclusive" and charge == "pim":
        raise ValueError(f"manifest row {row_number}: exclusive+pim is forbidden")
    if row["validation_status"].strip() != "VALID":
        raise ValueError(f"manifest row {row_number}: job is not VALID")

    expected_id = (
        f"mc_{reaction}_{row['pass'].strip()}_{charge}_{target}_"
        f"{row['setting_id'].strip()}"
    )
    if row["job_id"].strip() != expected_id:
        raise ValueError(
            f"manifest row {row_number}: job_id {row['job_id']!r} does not "
            f"match {expected_id!r}"
        )
    if Path(row["input_file"].strip()).name != f"{expected_id}.inp":
        raise ValueError(f"manifest row {row_number}: input_file basename mismatch")
    try:
        ngen = int(row["ngen"].strip())
    except ValueError as error:
        raise ValueError(f"manifest row {row_number}: invalid ngen") from error
    if ngen != EVENT_COUNTS[reaction]:
        raise ValueError(
            f"manifest row {row_number}: ngen={ngen}, expected "
            f"{EVENT_COUNTS[reaction]} for {reaction}"
        )


def render(text: str, row: Mapping[str, str]) -> str:
    replacements = {
        "ngen": row["ngen"].strip(),
        "Ebeam": mev(row["ebeam"], "ebeam"),
        "spec%e%P": mev(row["hms_p_magnitude"], "hms_p_magnitude"),
        "spec%e%theta": row["hms_th"].strip(),
        "spec%p%P": mev(row["shms_p_magnitude"], "shms_p_magnitude"),
        "spec%p%theta": row["shms_th"].strip(),
        "Egamma_gen_max": mev(row["ebeam"], "ebeam"),
    }
    rendered = text
    for name, value in replacements.items():
        rendered = replace_assignment(rendered, name, value)
    return rendered


def validate_rendered(
    text: str, row: Mapping[str, str], source: Path,
    reaction_flags: Mapping[tuple[str, str], Mapping[str, str]],
) -> None:
    reaction = row["reaction"].strip()
    charge = row["charge"].strip()
    target = row["target"].strip()
    validate_template(text, reaction, charge, target, source, reaction_flags)
    expected = {
        "ngen": Decimal(row["ngen"].strip()),
        "Ebeam": Decimal(mev(row["ebeam"], "ebeam")),
        "spec%e%P": Decimal(mev(row["hms_p_magnitude"], "hms_p_magnitude")),
        "spec%e%theta": Decimal(row["hms_th"].strip()),
        "spec%p%P": Decimal(mev(row["shms_p_magnitude"], "shms_p_magnitude")),
        "spec%p%theta": Decimal(row["shms_th"].strip()),
        "Egamma_gen_max": Decimal(mev(row["ebeam"], "ebeam")),
    }
    for name, value in expected.items():
        actual = decimal_value(assignment_value(text, name), f"rendered:{name}")
        if actual != value:
            raise ValueError(f"rendered {name}={actual}, expected {value}")


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            stream.write(text)
        os.replace(temporary_name, path)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-list", type=Path, required=True)
    parser.add_argument(
        "--reaction-flags", type=Path, default=DEFAULT_REACTION_FLAGS,
        help="CSV defining the SIMC flags for each reaction and charge",
    )
    parser.add_argument(
        "--template-dir",
        type=Path,
        required=True,
        help="directory containing the pre-Pass-1 coin .inp files",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--overwrite", action="store_true", help="replace existing generated inputs"
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        reaction_flags = load_reaction_flags(args.reaction_flags)
        templates = discover_templates(args.template_dir)
        rows = read_manifest(args.job_list)
        seen_outputs: set[Path] = set()
        counts: Counter[str] = Counter()
        rendered_jobs: list[tuple[Path, str]] = []
        for row_number, row in enumerate(rows, start=2):
            validate_manifest_row(row, row_number)
            reaction = row["reaction"].strip()
            charge = row["charge"].strip()
            target = row["target"].strip()
            template = templates[(reaction, charge, target)]
            template_text = template.read_text(encoding="utf-8")
            validate_template(
                template_text, reaction, charge, target, template, reaction_flags
            )
            rendered = render(template_text, row)
            validate_rendered(rendered, row, template, reaction_flags)
            output = args.output_dir / f"{row['job_id'].strip()}.inp"
            if output in seen_outputs:
                raise ValueError(f"duplicate output path: {output}")
            seen_outputs.add(output)
            if output.exists() and not args.overwrite and not args.dry_run:
                raise ValueError(f"output exists (use --overwrite): {output}")
            rendered_jobs.append((output, rendered))
            counts[reaction] += 1
    except (OSError, ValueError) as error:
        raise SystemExit(f"ERROR: {error}") from error

    summary = ", ".join(f"{name}={counts[name]}" for name in REACTIONS)
    print(f"Validated {len(templates)} template combinations")
    print(f"Prepared {len(rendered_jobs)} inputs ({summary})")
    if args.dry_run:
        print("Dry run: no files written")
        return 0
    for output, rendered in rendered_jobs:
        atomic_write(output, rendered)
    print(f"Wrote {len(rendered_jobs)} inputs under {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
