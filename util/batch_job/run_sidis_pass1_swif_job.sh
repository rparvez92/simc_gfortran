#!/bin/bash

set -eo pipefail

if [[ $# -ne 3 ]]; then
  echo "Usage: $0 <simc-dir> <job-list.csv> <job-id>" >&2
  exit 2
fi

simc_dir=$1
job_list=$2
job_id=$3

modules_script=/etc/profile.d/modules.sh
if [[ $(type -t module || true) != function && -r "$modules_script" ]]; then
  source "$modules_script"
fi
module purge
module use /group/c-rsidis/modulefiles/
module load hcana/1.5.2

root_version=$(root-config --version)
if [[ $root_version != 6.36.* ]]; then
  echo "ERROR: expected ROOT 6.36.x, found $root_version at $(command -v root-config)" >&2
  exit 2
fi

export TMPDIR=${TMPDIR:-/scratch/$USER}
mkdir -p "$TMPDIR"

cd "$simc_dir"
exec python3 util/batch_job/run_sidis_pass1_job.py \
  --simc-dir "$simc_dir" \
  --job-list "$job_list" \
  --job-id "$job_id" \
  --skip-existing
