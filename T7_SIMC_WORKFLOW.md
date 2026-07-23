# T7 SIMC workflow

Run `run_simc_recon.sh` from this checkout with an input path relative to
`infiles/`:

```sh
./run_simc_recon.sh \
  RP_Simc/coin/mc_delta_phase1_pass4_PIMINUS_LD2_x0p25Q23p3z0p5thpq2p0.inp \
  delta mpi 1
```

The runner infers `Phase1` or `Phase2` from the filename and the run type from
the input's immediate parent directory (`coin` in this example). Generated
products are written under:

```text
/Volumes/T7/RSIDIS/PhaseN/Simulation/outfiles/<run-type>/
/Volumes/T7/RSIDIS/PhaseN/Simulation/runout/<run-type>/
/Volumes/T7/RSIDIS/PhaseN/Simulation/ROOTfiles/<run-type>/
```

The local `outfiles`, `runout`, and `worksim` names are symlinks selected by
the runner. `worksim` points to the applicable T7 `ROOTfiles/<run-type>`
directory so that the existing `recon_hcana` path convention remains intact.
Only one run may execute at a time because these symlinks are shared.

Use `--ngen N` for a short validation without modifying the source input:

```sh
./run_simc_recon.sh RP_Simc/coin/example_phase2_input.inp delta mpi 1 --ngen 100
```

Existing output sets are protected by default. Pass `--overwrite` explicitly
to replace one. Set `SIMC_T7_ROOT` if T7 is mounted somewhere other than
`/Volumes/T7/RSIDIS`.
