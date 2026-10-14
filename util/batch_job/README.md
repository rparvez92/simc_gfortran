# Pass-1 R-SIDIS batch production

This directory contains the reproducible job-list, input-generation, single-job,
and SWIF2 submission tools for the Pass-1 SIMC production.

## Layout

- `source_files/`: authoritative input CSV metadata, including the reaction
  flag table consumed by the input generator.
- `build_simc_job_list.py`: builds `simc_job_list_pass1.csv`.
- `simc_job_list_pass1.csv`: generated 492-row manifest.
- `generate_sidis_pass1_inputs.py`: renders the canonical files under
  `infiles/Pass1/coin/`.
- `run_sidis_pass1_job.py`: runs and validates one manifest job.
- `run_sidis_pass1_swif_job.sh`: initializes the farm software environment.
- `submit_sidis_pass1_swif2.py`: preflights and submits the current production.

The manifest contains all four reactions for reproducibility. Event counts are
100,000 for SIDIS and 10,000 for rho, delta, and exclusive. The current SWIF2
submission deliberately excludes all rho rows, leaving 354 submitted jobs:
138 SIDIS, 138 delta, and 78 exclusive.

SIMC still requires its runtime `.inp` files under `infiles/`; keeping the
generator and metadata here does not change that runtime interface.
