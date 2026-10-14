#!/usr/bin/env python3
"""Run one Pass-1 SIMC job and recon_hcana safely by manifest job_id."""

from __future__ import annotations

import argparse
import csv
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


SIMC_DIR = Path(__file__).resolve().parents[2]
REACTIONS = {"sidis", "rho", "delta", "exclusive"}


def load_job(path: Path, job_id: str) -> dict[str, str]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        rows = [row for row in reader if row.get("job_id") == job_id]
    if len(rows) != 1:
        raise ValueError(f"expected one manifest row for {job_id}, found {len(rows)}")
    row = rows[0]
    if row.get("validation_status") != "VALID":
        raise ValueError(f"manifest job is not VALID: {job_id}")
    if row.get("reaction") not in REACTIONS:
        raise ValueError(f"invalid reaction for {job_id}: {row.get('reaction')!r}")
    expected = (
        f"mc_{row['reaction']}_{row['pass']}_{row['charge']}_"
        f"{row['target']}_{row['setting_id']}"
    )
    if job_id != expected:
        raise ValueError(f"job_id does not match manifest fields: {job_id}")
    return row


def replace_ngen(text: str, ngen: int) -> str:
    pattern = re.compile(r"^(\s*ngen\s*=\s*)[^;\r\n]+", re.MULTILINE)
    result, count = pattern.subn(lambda match: match.group(1) + str(ngen), text)
    if count != 1:
        raise ValueError(f"expected one ngen assignment, found {count}")
    return result


def has_h10(rootls: str, path: Path) -> bool:
    result = subprocess.run(
        [rootls, "-1", str(path)], text=True, capture_output=True, check=False
    )
    return result.returncode == 0 and "h10" in result.stdout.split()


def has_expected_entries(root: str, path: Path, expected: int) -> bool:
    if not path.is_file():
        return False
    escaped = str(path).replace("\\", "\\\\").replace('"', '\\"')
    expression = (
        f'TFile f("{escaped}","READ");'
        'auto *t=dynamic_cast<TTree*>(f.Get("h10"));'
        f'gSystem->Exit(!f.IsZombie()&&t&&t->GetEntries()=={expected}?0:1);'
    )
    result = subprocess.run(
        [root, "-l", "-b", "-q", "-e", expression],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-list", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--simc-dir", type=Path, default=SIMC_DIR)
    parser.add_argument("--ngen", type=int, help="smoke-test override")
    existing = parser.add_mutually_exclusive_group()
    existing.add_argument("--overwrite", action="store_true")
    existing.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.ngen is not None and args.ngen <= 0:
        raise SystemExit("ERROR: --ngen must be positive")
    simc_dir = args.simc_dir.resolve()
    try:
        row = load_job(args.job_list, args.job_id)
        input_rel = Path(row["input_file"])
        if input_rel.is_absolute() or ".." in input_rel.parts:
            raise ValueError(f"unsafe manifest input path: {input_rel}")
        canonical_input = simc_dir / input_rel
        if not canonical_input.is_file():
            raise ValueError(f"input does not exist: {canonical_input}")
        simc = simc_dir / "simc"
        run_simc_tree = simc_dir / "run_simc_tree"
        make_root_tree = simc_dir / "util" / "root_tree" / "make_root_tree"
        recon_source = simc_dir / "util" / "recon_hcana"
        for executable in (simc, run_simc_tree, make_root_tree):
            if not executable.is_file() or not os.access(executable, os.X_OK):
                raise ValueError(f"required executable is missing: {executable}")
        root = shutil.which("root")
        rootls = shutil.which("rootls")
        if root is None or rootls is None:
            raise ValueError("root and rootls must be available in PATH")
        root_probe = subprocess.run(
            [root, "-l", "-b", "-q", "-e", "gSystem->Exit(0);"],
            text=True,
            capture_output=True,
            check=False,
        )
        if root_probe.returncode != 0:
            detail = (root_probe.stderr or root_probe.stdout).strip().splitlines()
            message = detail[0] if detail else f"exit code {root_probe.returncode}"
            raise ValueError(f"ROOT/Cling runtime probe failed: {message}")
        for name in ("outfiles", "runout", "worksim"):
            directory = simc_dir / name
            if not directory.is_dir() or not os.access(directory, os.W_OK):
                raise ValueError(f"required writable directory is unavailable: {directory}")
    except (OSError, ValueError) as error:
        raise SystemExit(f"ERROR: {error}") from error

    stem = args.job_id
    reaction = row["reaction"]
    expected_entries = args.ngen if args.ngen is not None else int(row["ngen"])
    staged_input = simc_dir / "infiles" / f"{stem}.inp"
    hist = simc_dir / "outfiles" / f"{stem}.hist"
    raw_bin = simc_dir / "worksim" / f"{stem}.bin"
    raw_root = simc_dir / "worksim" / f"{stem}.root"
    recon_root = simc_dir / "worksim" / f"recon_hcana_{stem}.root"
    run_log = simc_dir / "runout" / f"{stem}.out"
    outputs = (hist, raw_root, recon_root, run_log)

    print(f"job_id={stem}")
    print(f"input={canonical_input}")
    print(f"reaction={reaction}")
    print(f"ngen={args.ngen if args.ngen is not None else row['ngen']}")
    for output in outputs:
        print(f"output={output}")
    if args.dry_run:
        print("Dry run: no files written and no processes started")
        return 0
    if args.skip_existing and all(path.is_file() for path in (hist, run_log)):
        if (has_expected_entries(root, raw_root, expected_entries)
                and has_expected_entries(root, recon_root, expected_entries)):
            print(f"SKIP: validated outputs already exist for {stem}")
            return 0
    existing = [path for path in (*outputs, raw_bin) if path.exists()]
    if existing and not args.overwrite:
        raise SystemExit(f"ERROR: output exists (use --overwrite): {existing[0]}")
    if args.overwrite:
        for path in existing:
            path.unlink()

    lock = simc_dir / "infiles" / f".{stem}.lock"
    lock_fd: int | None = None
    scratch: Path | None = None
    try:
        lock_fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        text = canonical_input.read_text(encoding="utf-8")
        if args.ngen is not None:
            text = replace_ngen(text, args.ngen)
        staged_input.write_text(text, encoding="utf-8")

        subprocess.run([str(run_simc_tree), stem], cwd=simc_dir, check=True)
        if not hist.is_file() or not raw_root.is_file():
            raise RuntimeError("SIMC did not create the expected histogram and ROOT file")
        if not has_expected_entries(root, raw_root, expected_entries):
            raise RuntimeError(
                f"raw SIMC ROOT file does not contain {expected_entries} h10 entries: {raw_root}"
            )

        scratch = Path(tempfile.mkdtemp(prefix=f"recon-{stem}.", dir=os.getenv("TMPDIR")))
        scratch_recon = scratch / "util" / "recon_hcana"
        scratch_recon.mkdir(parents=True)
        shutil.copy2(recon_source / "recon_hcana.h", scratch_recon / "recon_hcana.h")
        shutil.copy2(recon_source / "recon_hcana.C", scratch_recon / "recon_hcana.C")
        shutil.copy2(
            Path(__file__).resolve().parent / "run_recon_hcana.C",
            scratch_recon / "run_recon_hcana.C",
        )
        (scratch / "outfiles").symlink_to(simc_dir / "outfiles", target_is_directory=True)
        (scratch / "worksim").symlink_to(simc_dir / "worksim", target_is_directory=True)
        macro = (
            f'run_recon_hcana.C+("{stem}","{reaction}","mpi",kTRUE)'
        )
        subprocess.run([root, "-l", "-b", "-q", macro], cwd=scratch_recon, check=True)
        if not has_expected_entries(root, recon_root, expected_entries):
            raise RuntimeError(
                f"recon ROOT file does not contain {expected_entries} h10 entries: {recon_root}"
            )
    except FileExistsError as error:
        raise SystemExit(f"ERROR: this job is already active: {lock}") from error
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"ERROR: job failed: {error}") from error
    finally:
        if staged_input.exists():
            staged_input.unlink()
        if scratch is not None:
            shutil.rmtree(scratch, ignore_errors=True)
        if lock_fd is not None:
            os.close(lock_fd)
        if lock.exists():
            lock.unlink()

    print(f"Completed {stem}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
