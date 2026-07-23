#!/bin/bash
# Run SIMC and recon_hcana while keeping generated products on T7.
#
# Usage:
#   ./run_simc_recon.sh <input-relative-to-infiles> <reaction> \
#       [hadron_type] [Earm_HMS] [--ngen N] [--overwrite]
#
# Example:
#   ./run_simc_recon.sh \
#     RP_Simc/coin/mc_delta_phase1_pass4_PIMINUS_LD2_x0p25Q23p3z0p5thpq2p0.inp \
#     delta mpi 1

set -euo pipefail

usage() {
  cat <<'EOF'
Usage: run_simc_recon.sh <input-relative-to-infiles> <reaction> [hadron_type] [Earm_HMS] [--ngen N] [--overwrite]

  input          Path relative to infiles/; absolute paths and '..' are rejected
  reaction       heep | sidis | rho | delta | exclusive | ...
  hadron_type    mpi (default) or mk
  Earm_HMS       1 (default; electron in HMS) or 0 (electron in SHMS)
  --ngen N       Override ngen in the staged copy (useful for smoke tests)
  --overwrite    Permit replacement of an existing T7 output set

The phase is read from '_phase1_' or '_phase2_' in the input filename. The
run type is the input's immediate parent directory (for example, coin or heep).
Set SIMC_T7_ROOT to override /Volumes/T7/RSIDIS.
EOF
}

if [ "$#" -lt 2 ]; then
  usage >&2
  exit 2
fi

INPUT_REL=$1
REACTION=$2
shift 2
HADRON_TYPE=mpi
EARM_HMS_INT=1
OVERWRITE=0
NGEN_OVERRIDE=
POSITIONAL_COUNT=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --overwrite)
      OVERWRITE=1
      shift
      ;;
    --ngen)
      if [ "$#" -lt 2 ]; then
        echo "ERROR: --ngen requires a positive integer." >&2
        exit 2
      fi
      NGEN_OVERRIDE=$2
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    --*)
      echo "ERROR: unknown option: $1" >&2
      exit 2
      ;;
    *)
      POSITIONAL_COUNT=$((POSITIONAL_COUNT + 1))
      case "$POSITIONAL_COUNT" in
        1) HADRON_TYPE=$1 ;;
        2) EARM_HMS_INT=$1 ;;
        *)
          echo "ERROR: unexpected argument: $1" >&2
          exit 2
          ;;
      esac
      shift
      ;;
  esac
done

case "$NGEN_OVERRIDE" in
  '') ;;
  *[!0-9]*|0)
    echo "ERROR: --ngen requires a positive integer, got: $NGEN_OVERRIDE" >&2
    exit 2
    ;;
esac

case "$INPUT_REL" in
  /*|../*|*/../*|*/..|..)
    echo "ERROR: input must be a safe path relative to infiles/: $INPUT_REL" >&2
    exit 2
    ;;
esac

case "$EARM_HMS_INT" in
  0) EARM_FLAG=kFALSE ;;
  1) EARM_FLAG=kTRUE ;;
  *)
    echo "ERROR: Earm_HMS must be 0 or 1, got: $EARM_HMS_INT" >&2
    exit 2
    ;;
esac

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
SIMC_DIR=$SCRIPT_DIR
SIMC_INFILES_DIR=$SIMC_DIR/infiles
SIMC_ROOT_TREE_DIR=$SIMC_DIR/util/root_tree
RECON_DIR=$SIMC_DIR/util/recon_hcana
T7_ROOT=${SIMC_T7_ROOT:-/Volumes/T7/RSIDIS}

case "$INPUT_REL" in
  *.inp) ;;
  *) INPUT_REL=${INPUT_REL}.inp ;;
esac

INPUT_FILE=$SIMC_INFILES_DIR/$INPUT_REL
if [ ! -f "$INPUT_FILE" ]; then
  echo "ERROR: input file not found: $INPUT_FILE" >&2
  exit 1
fi

INPUT_NAME=${INPUT_REL##*/}
STEM=${INPUT_NAME%.inp}
RUN_TYPE=$(basename -- "$(dirname -- "$INPUT_REL")")
case "$RUN_TYPE" in
  .|infiles|RP_Simc|''|*[!A-Za-z0-9_-]*)
    echo "ERROR: cannot infer a safe run type from input path: $INPUT_REL" >&2
    echo "Place the input below a run-type directory such as RP_Simc/coin/." >&2
    exit 2
    ;;
esac

case "$INPUT_NAME" in
  *_phase1_*) PHASE=Phase1 ;;
  *_phase2_*) PHASE=Phase2 ;;
  *)
    echo "ERROR: filename must contain '_phase1_' or '_phase2_': $INPUT_NAME" >&2
    exit 2
    ;;
esac

if [ ! -d "$T7_ROOT" ]; then
  echo "ERROR: T7 root is unavailable; is the volume mounted? $T7_ROOT" >&2
  exit 1
fi

T7_SIM_DIR=$T7_ROOT/$PHASE/Simulation
T7_OUTFILES_DIR=$T7_SIM_DIR/outfiles/$RUN_TYPE
T7_RUNOUT_DIR=$T7_SIM_DIR/runout/$RUN_TYPE
T7_ROOTFILES_DIR=$T7_SIM_DIR/ROOTfiles/$RUN_TYPE

for directory in "$T7_OUTFILES_DIR" "$T7_RUNOUT_DIR" "$T7_ROOTFILES_DIR"; do
  mkdir -p "$directory"
  if [ ! -w "$directory" ]; then
    echo "ERROR: T7 output directory is not writable: $directory" >&2
    exit 1
  fi
done

LOCK_DIR=$SIMC_DIR/.run_simc_recon.lock
STAGED_INPUT=
cleanup() {
  status=$?
  if [ -n "$STAGED_INPUT" ] && [ -f "$STAGED_INPUT" ]; then
    rm -f "$STAGED_INPUT"
  fi
  rmdir "$LOCK_DIR" 2>/dev/null || true
  exit "$status"
}

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "ERROR: another run_simc_recon.sh process is active: $LOCK_DIR" >&2
  exit 1
fi
trap cleanup EXIT HUP INT TERM

for local_name in outfiles runout worksim; do
  local_path=$SIMC_DIR/$local_name
  if [ -e "$local_path" ] && [ ! -L "$local_path" ]; then
    echo "ERROR: refusing to replace non-symlink path: $local_path" >&2
    exit 1
  fi
done

ln -sfn "$T7_OUTFILES_DIR" "$SIMC_DIR/outfiles"
ln -sfn "$T7_RUNOUT_DIR" "$SIMC_DIR/runout"
ln -sfn "$T7_ROOTFILES_DIR" "$SIMC_DIR/worksim"

for output in \
  "$T7_OUTFILES_DIR/$STEM.hist" \
  "$T7_RUNOUT_DIR/$STEM.out" \
  "$T7_ROOTFILES_DIR/$STEM.root" \
  "$T7_ROOTFILES_DIR/recon_hcana_$STEM.root"; do
  if [ -e "$output" ] && [ "$OVERWRITE" -ne 1 ]; then
    echo "ERROR: output already exists (use --overwrite): $output" >&2
    exit 1
  fi
done

STAGED_INPUT=$SIMC_INFILES_DIR/$INPUT_NAME
if [ "$INPUT_FILE" != "$STAGED_INPUT" ]; then
  if [ -e "$STAGED_INPUT" ]; then
    echo "ERROR: staging input already exists: $STAGED_INPUT" >&2
    exit 1
  fi
  cp "$INPUT_FILE" "$STAGED_INPUT"
else
  STAGED_INPUT=
fi

printf '%s\n' \
  "=========================================" \
  " Running SIMC + recon_hcana" \
  " Input:       $INPUT_REL" \
  " Phase:       $PHASE" \
  " Run type:    $RUN_TYPE" \
  " Reaction:    $REACTION" \
  " Hadron type: $HADRON_TYPE" \
  " Earm_HMS:    $EARM_FLAG" \
  " ngen:        ${NGEN_OVERRIDE:-input default}" \
  " T7 output:   $T7_SIM_DIR" \
  "========================================="

echo ">>> [1/4] Converting staged SIMC input"
(
  cd "$SIMC_INFILES_DIR"
  ./convert_inputfile.sh "$INPUT_NAME"
)

if [ -n "$NGEN_OVERRIDE" ]; then
  override_file=$(mktemp "${TMPDIR:-/tmp}/simc-ngen.XXXXXX")
  if ! awk -v ngen="$NGEN_OVERRIDE" '
    BEGIN { changed = 0 }
    !changed && $0 ~ /^[[:space:]]*ngen[[:space:]]*=/ {
      sub(/[0-9]+/, ngen)
      changed = 1
    }
    { print }
    END { if (!changed) exit 3 }
  ' "$SIMC_INFILES_DIR/$INPUT_NAME" > "$override_file"; then
    rm -f "$override_file"
    echo "ERROR: could not override ngen in staged input." >&2
    exit 1
  fi
  mv "$override_file" "$SIMC_INFILES_DIR/$INPUT_NAME"
fi

echo ">>> [2/4] Building SIMC ROOT tree"
(
  cd "$SIMC_ROOT_TREE_DIR"
  make clean
  make
)

echo ">>> [3/4] Running SIMC"
(
  cd "$SIMC_DIR"
  ./run_simc_tree "$STEM"
)

HIST_FILE=$T7_OUTFILES_DIR/$STEM.hist
ROOT_FILE=$T7_ROOTFILES_DIR/$STEM.root
if [ ! -f "$HIST_FILE" ] || [ ! -f "$ROOT_FILE" ]; then
  echo "ERROR: SIMC did not create the expected .hist and .root files." >&2
  exit 1
fi

echo ">>> [4/4] Running recon_hcana"
RECON_FILE=$T7_ROOTFILES_DIR/recon_hcana_$STEM.root
(
  cd "$RECON_DIR"
  root -l -b -q "run_recon_hcana.C+(\"$STEM\",\"$REACTION\",\"$HADRON_TYPE\",$EARM_FLAG)"
)

if [ ! -f "$RECON_FILE" ]; then
  echo "ERROR: recon_hcana output not found: $RECON_FILE" >&2
  exit 1
fi
if ! rootls -1 "$RECON_FILE" 2>/dev/null | grep -qx h10; then
  echo "ERROR: recon_hcana output does not contain a readable h10 tree: $RECON_FILE" >&2
  exit 1
fi

printf '%s\n' \
  "Run completed successfully:" \
  "  SIMC input:       $INPUT_FILE" \
  "  SIMC histogram:   $HIST_FILE" \
  "  SIMC ROOT file:   $ROOT_FILE" \
  "  recon_hcana ROOT: $RECON_FILE" \
  "  run log:          $T7_RUNOUT_DIR/$STEM.out"
