# SIMC yield physics: from beam charge to a Monte Carlo prediction

This note explains what a SIMC yield means, why it can be compared with a
data yield, and how `Ngen`, `Ntried`, `Weight`, `normfac`, and `fWeight` fit
together.  The main example is a positive-`Ngen` SIDIS coincidence run.

The central idea is:

> Data count physical interactions produced by a measured luminosity. SIMC
> numerically integrates a cross-section model over the same experimental
> phase space and detector acceptance. They can therefore be expressed in
> the same unit: predicted counts (or counts per unit charge).

SIMC does not need to reproduce individual beam bunches, ionization, or ADC
pulses to make this prediction. It samples the variables in the event-rate
integral and transports the resulting particles through a model of the
spectrometers.

## 1. Quantities called "yield"

Several different quantities are casually called a yield. Keep their names
and units explicit.

### 1.1 Data quantities

For one run or run group:

- `N_raw`: events passing the analysis cuts before background subtraction or
  efficiency correction.
- `N_bg`: estimated events from random coincidences, target walls, charge-
  symmetric background, or other sources that are not part of the desired
  reaction.
- `N_net = N_raw - N_bg`: background-subtracted events.
- `Q`: accepted integrated beam charge, commonly in mC.
- `epsilon_data`: product of the applicable data efficiencies and live-time
  factors.
- `N_corr = N_net / epsilon_data`: the number corrected to the chosen ideal
  data convention.
- `Y_data^Q = N_corr / Q`: charge-normalized yield, for example counts/mC.

If the target density during production was a fraction `f_rho` of the target
density used by SIMC, there are two equivalent conventions:

1. use the effective target thickness `f_rho * t_nominal` in SIMC, and do not
   density-correct the data; or
2. use the nominal target thickness in SIMC and divide the data by `f_rho`.

Do one, not both. In convention 2 a schematic corrected data yield is

```text
Y_data^Q = (N_raw - N_bg)
           / (Q * LT * epsilon_trigger * epsilon_track * epsilon_PID
                * epsilon_detector * f_rho).
```

Not every experiment uses exactly this bookkeeping. For example, a target-
wall contribution is normally subtracted rather than represented by an
"efficiency." The important requirement is that data and SIMC describe the
same idealized measurement.

### 1.2 Luminosity and absolute yield

For an incident electron flux and a target with areal number density `n_t`,

$$
  \mathcal L_{\rm int} = N_e n_t, \qquad N_e=\frac{Q}{e}.
$$

For a differential cross section in variables $\Phi$, the predicted count
is

$$
  N_{\rm pred}=\mathcal L_{\rm int}
    \int_R \frac{d\sigma}{d\Phi}
    A(\Phi)\,\epsilon(\Phi)\,d\Phi .
$$

Here `R` is the generated region, `A` includes geometrical and reconstruction
acceptance, and `epsilon` contains effects represented in the simulation.
The result is a number of counts, not a cross section.

The local SIMC source constructs a target conversion factor from the target
mass, abundance, angle, and thickness, then computes

```fortran
luminosity = EXPER%charge/targetfac
```

in `simc.f`. `EXPER%charge` is in mC and `luminosity` is reported in
microbarn inverse. Thus, charge is an actual SIMC input. Setting it to 1 mC
asks SIMC for a prediction normalized to 1 mC; it does **not** mean that SIMC
has simulated one physical coulomb, one beam bunch, or one electron at a
time.

### 1.3 Two equivalent comparison conventions

One may compare absolute counts at the data charge:

$$
  N_{\rm data,corr}\quad\text{with}\quad
  N_{\rm SIMC}(Q_{\rm data}),
$$

or compare charge-normalized yields:

$$
  \frac{N_{\rm data,corr}}{Q_{\rm data}}
  \quad\text{with}\quad
  \frac{N_{\rm SIMC}(Q_{\rm SIMC})}{Q_{\rm SIMC}}.
$$

Because the SIMC luminosity is linear in `EXPER%charge`, these are equivalent
when all other conventions match. Running SIMC with 1 mC simply makes its
summed yield numerically equal to a prediction in counts/mC.

## 2. Why compare a SIMC yield with a data yield?

A cross section is not observed directly. The experiment observes events
after finite acceptance, radiation, energy loss, resolution, reconstruction,
and cuts. A point cross section evaluated only at the central kinematics does
not generally predict that event count.

SIMC performs the convolution needed to connect the physics model to the
measurement. Consequently, an absolute data/SIMC yield comparison tests the
combined description of:

- integrated luminosity and target thickness;
- the differential cross-section model across the accepted phase space;
- radiative effects, energy loss, multiple scattering, and particle decay;
- spectrometer optics, apertures, reconstruction, and resolution;
- analysis cuts and the remaining data efficiency corrections.

This is both the strength and the limitation of a yield ratio. A discrepancy
does not by itself identify which item is wrong. Kinematic distributions and
systematic variations are needed for diagnosis.

Shape agreement alone is weaker than absolute agreement. Histograms can be
arbitrarily area-normalized and have matching shapes even if the luminosity,
cross-section magnitude, target thickness, or an overall efficiency is
incorrect. Conversely, one integrated number can agree while compensating
shape errors cancel across the acceptance. A useful validation checks both.

## 3. SIMC as Monte Carlo integration

### 3.1 The elementary estimator

Suppose SIMC throws points uniformly in a generated phase-space region with
volume

$$
  V_{\rm gen}=\int_R d\Phi.
$$

Let $I_i$ equal one when throw `i` survives the simulated acceptance and
the analysis selection, and zero otherwise. Let $w_i$ contain the physics
integrand and any Jacobian or generation correction. Uniform Monte Carlo
integration gives

$$
  N_{\rm pred}\simeq
  \mathcal L_{\rm int}\frac{V_{\rm gen}}{N_{\rm tried}}
  \sum_{i=1}^{N_{\rm tried}} I_i w_i
  =\mathcal L_{\rm int}\frac{V_{\rm gen}}{N_{\rm tried}}
  \sum_{i\in\mathrm{selected}} w_i.
$$

This equation explains why failed throws matter even though no failed event
appears in the final selected histogram: every random point belongs in the
denominator `Ntried`. Replacing `Ntried` with the number of accepted events
would remove the acceptance loss and bias the integral.

This also explains why an unweighted count of SIMC tree entries is not the
SIMC yield. Tree entries are integration samples, not equivalent physical
events.

### 3.2 Event lifecycle in the local SIMC implementation

For each loop iteration, `simc.f`:

1. increments `ntried`;
2. calls `generate`, which samples the generated variables and completes the
   reaction kinematics;
3. if generation succeeds, calls `montecarlo` to transport the particles
   through target and spectrometer effects;
4. reconstructs the event and checks spectrometer-population and physics
   cuts;
5. writes a diagnostic ntuple entry according to the configured output mode;
6. increments the successful-event counter only according to the `ngen`
   mode.

Within event generation and completion, the code can apply radiation,
multiple scattering, energy loss, optics and apertures, decay, spectral or
target factors, reaction cross sections, and coordinate Jacobians. SIMC is
therefore an acceptance-aware physics Monte Carlo, but it is not a full
GEANT detector-response simulation: ordinary data acquisition and detector
efficiencies still need appropriate data-side treatment unless explicitly
modeled.

## 4. `Ntried`, `Ngen`, successes, and tree entries

These quantities have different meanings.

### 4.1 Positive `ngen`

The input files document positive `ngen` as the requested number of
successes. The event loop condition is

```fortran
do while (nevent.lt.abs(ngen))
```

and, for positive `ngen`, `nevent` increments only when `success` is true.
Therefore the run continues until

$$
  N_{\rm success}=N_{\rm gen},
$$

while generally

$$
  N_{\rm tried}\ge N_{\rm gen}.
$$

The ratio `Ngen/Ntried` is the overall success fraction for the stages that
control `success`. It is not an efficiency to apply to data; it is part of
the Monte Carlo integration bookkeeping.

### 4.2 Negative `ngen`

For negative `ngen`, `nevent` increments on every loop iteration, whether or
not the throw succeeds. The program consequently makes exactly `abs(ngen)`
attempts. This mode is useful when poor acceptance might otherwise make SIMC
search indefinitely for a requested number of successes.

The `recon_hcana` helper only creates a nonzero `fWeight` when its parsed
`Ngen` is positive. The positive-`Ngen` formula in this note must therefore
not be blindly applied to a negative-`Ngen` output. For production yield
work, use a positive `ngen` unless the downstream normalization has been
explicitly designed for fixed-attempt mode.

### 4.3 ROOT entries and later analysis cuts

`Ngen` is a run-control count; `Ntried` is an attempted-throw count. A ROOT
tree entry is an output record. Their equality depends on the output path and
success/write logic. Furthermore, a later ROOT selection can retain only a
subset of stored entries.

Never normalize by `tree->GetEntries()` merely because it is convenient.
Use the SIMC normalization metadata, and calculate a selected-bin yield by
summing the per-entry normalized weights for entries passing that bin's
cuts.

## 5. SIDIS generation volume

The code approximates each arm's angular measure in target slopes as

$$
  \Delta\Omega_e =
  (y'_{e,\max}-y'_{e,\min})(x'_{e,\max}-x'_{e,\min}),
$$

$$
  \Delta\Omega_h =
  (y'_{h,\max}-y'_{h,\min})(x'_{h,\max}-x'_{h,\min}).
$$

For `doing_semi`, the local `simc.f` constructs

$$
  V_{\rm gen}=
  \Delta\Omega_e\,\Delta\Omega_h\,
  \Delta E_{e'}\,\Delta E_h.
$$

Thus the SIDIS generation is six-dimensional: two electron angles, scattered
electron energy, two hadron angles, and hadron energy. In the code's native
convention the angular slopes are in radians and the energy ranges are in
MeV, so the generation volume carries the corresponding powers of sr and
MeV. The units cancel those of the differential cross section and event
weight so that the final luminosity-weighted result is a count.

The generated region is not identical to the accepted region. It should
cover the relevant acceptance; transport and cuts then determine which
throws survive.

For hydrogen `H(e,e'p)`, the generated volume starts with only the electron
angular volume in this normalization block. Other reaction modes multiply
different energy and hadron-angle factors, which is why one must not copy a
SIDIS `genvol` formula into every reaction.

## 6. What the stored `Weight` means

Near the end of `complete_main` in `event.f`, the local code forms

```fortran
main%weight = main%SF_weight*main%jacobian*main%gen_weight*main%sigcc
main%weight = main%weight * tgtweight
```

and, for a kaon mode in which decay is not explicitly simulated, also
multiplies a survival probability. Schematically,

$$
  w_i = w_{{\rm SF},i}\,J_i\,w_{{\rm gen},i}\,
        \sigma_i\,w_{{\rm target},i}\,w_{{\rm survival},i}.
$$

- `sigcc` is the reaction-dependent differential cross-section model at the
  event kinematics, including the code's configured corrections.
- `jacobian` transforms between the variables used by the cross-section
  model and those sampled or reconstructed by SIMC.
- `gen_weight` corrects event-by-event restrictions of a nominal generation
  interval. It starts at one and is modified when kinematics narrow an
  allowed energy interval.
- `SF_weight` represents the spectral-function factor for applicable nuclear
  reactions; it is one for modes such as SIDIS in this branch of the code.
- `tgtweight` converts an appropriate per-nucleon model to the configured
  target content where required.
- a survival factor can represent a decay probability when decay is weighted
  instead of explicitly generated.

`Weight` is therefore primarily the value of the integration integrand for
one sampled point. It does **not** include the complete generated volume, the
integrated luminosity, or the division by the total number of random throws.
Consequently, `sum(Weight)` by itself is neither an absolute count nor a
charge-normalized yield.

Acceptance is also not generally a continuous factor inside `Weight`.
Transport failures and cuts most often act as a zero/one decision: a failed
throw contributes zero, while a surviving throw contributes its weight.

## 7. `normfac`, `fWeight`, and the SIMC yield

For a standard positive-`ngen` run, `simc.f` calculates

```fortran
normfac = luminosity/ntried*nevent
...
normfac = normfac * genvol
```

At normal completion `nevent = Ngen`, so

$$
  \texttt{normfac}
  =\mathcal L_{\rm int}\frac{N_{\rm gen}}{N_{\rm tried}}V_{\rm gen}.
$$

Why put `Ngen` into `normfac` only to divide by it later? Historically,
SIMC's integrated weight accumulator contains a sum over successful events,
and this normalization converts its average-over-successes structure into
the full attempted-volume integral. The ROOT helper exposes the same result
as a convenient per-entry quantity:

```cpp
fWeight = Weight * simc_normfactor / simc_nevents;
```

Algebraically,

$$
  \texttt{fWeight}_i
  =w_i\frac{\texttt{normfac}}{N_{\rm gen}}
  =w_i\frac{\mathcal L_{\rm int}V_{\rm gen}}{N_{\rm tried}}.
$$

Therefore the predicted yield in any selected bin or region `B` is

$$
  Y_{{\rm SIMC},B}=\sum_{i\in B}\texttt{fWeight}_i.
$$

One `fWeight` is one Monte Carlo sample's contribution to the integral. It
is not the whole yield. The unweighted number of selected SIMC entries is
also not the yield.

### Important special mode: `doing_phsp`

The source explicitly sets `normfac = 1.0` when `doing_phsp` is true. That
mode is intended for phase-space studies and bypasses the standard absolute
normalization. Do not interpret its `Weight*normfac/Ngen` as the production
yield formula derived above without a separate definition for that study.

## 8. Worked SIDIS coincidence example

The following is a deliberately small toy example. Its units are chosen to
be mutually consistent, but its numerical values are illustrative rather
than representative of a particular experiment.

### 8.1 SIMC configuration and normalization

Suppose a SIDIS SIMC run uses:

```text
EXPER%charge = 1.0 mC
luminosity   = 2500 /microbarn
Ntried       = 100000
Ngen         = 40000 successful events
genvol       = 0.020 sr^2 MeV^2
```

The success fraction is `40000/100000 = 0.4`, and

$$
  \texttt{normfac}
  =2500\times0.4\times0.020=20.
$$

The common per-event integration factor is

$$
  \frac{\texttt{normfac}}{N_{\rm gen}}
  =\frac{20}{40000}=5.0\times10^{-4},
$$

which is also

$$
  \frac{\mathcal L V_{\rm gen}}{N_{\rm tried}}
  =\frac{2500\times0.020}{100000}=5.0\times10^{-4}.
$$

After a tight analysis-bin cut, suppose five stored events survive:

| Event | `Weight` | `fWeight = Weight x 0.0005` (counts at 1 mC) |
|---:|---:|---:|
| 1 | 520 | 0.260 |
| 2 | 480 | 0.240 |
| 3 | 650 | 0.325 |
| 4 | 450 | 0.225 |
| 5 | 700 | 0.350 |
| **Sum** | **2800** | **1.400** |

The SIMC result for the bin is therefore

$$
  Y_{\rm SIMC}^{Q}=1.400\ \text{counts/mC}.
$$

This illustrates the role of rejected events. The final table contains only
five selected entries, but the integration denominator remains 100000 total
throws. Using five, 40000, or the total ROOT entries in its place would give
a different and incorrect result.

### 8.2 Corrected data yield

Suppose the matching data sample has

```text
Q                  = 12.0 mC
N_raw              = 20 events
N_bg               = 2 events
DAQ live time      = 0.92
trigger efficiency = 0.99
tracking efficiency= 0.96
PID efficiency     = 0.98
detector efficiency= 0.995
relative density   = 0.97
```

Here SIMC uses the nominal target thickness, so the data are corrected to
nominal density. The total correction factor is

$$
  \epsilon_{\rm data}
  =0.92\times0.99\times0.96\times0.98\times0.995\times0.97
  =0.827018.
$$

Thus

$$
  N_{\rm data,corr}=\frac{20-2}{0.827018}=21.765
$$

and

$$
  Y_{\rm data}^{Q}=\frac{21.765}{12.0}
  =1.814\ \text{counts/mC}.
$$

### 8.3 Absolute-count and per-charge comparisons

Rescaling the 1 mC SIMC result to the data charge gives

$$
  N_{\rm SIMC}(12\ \mathrm{mC})=1.400\times12=16.800.
$$

The absolute-count ratio is

$$
  R=\frac{21.765}{16.800}=1.296.
$$

The per-charge ratio is identically

$$
  R=\frac{1.814}{1.400}=1.296.
$$

The two conventions contain the same physics. A ratio above one means that,
under the stated corrections and cuts, data exceed the SIMC prediction by
about 30%. It does not prove that the cross-section model alone is low;
luminosity, target, efficiencies, backgrounds, acceptance, and radiative
modeling must also be considered.

### 8.4 Weighted Monte Carlo statistical uncertainty

For independent weighted samples, the usual Monte Carlo variance estimate
for the selected sum is

$$
  \delta Y_{\rm SIMC}=\sqrt{\sum_i \texttt{fWeight}_i^2}.
$$

For the five toy events,

$$
  \delta Y_{\rm SIMC}
  =\sqrt{0.260^2+0.240^2+0.325^2+0.225^2+0.350^2}
  =0.636\ \text{counts/mC}.
$$

The effective number of equally weighted events is

$$
  N_{\rm eff}=\frac{(\sum_i f_i)^2}{\sum_i f_i^2}
  =\frac{1.400^2}{0.40395}=4.85.
$$

This intentionally tiny example has a 45% relative SIMC statistical error.
A production run should generate enough events that this uncertainty is
small compared with the desired experimental precision in every reported
bin.

For a simplified illustration in which the background estimate has no
uncertainty, take `sqrt(N_net)` as the data counting uncertainty. After the
same corrections,

$$
  \delta Y_{\rm data}^{Q}
  =\frac{\sqrt{18}}{12\times0.827018}=0.428\ \text{counts/mC}.
$$

If data and Monte Carlo statistics are independent,

$$
  \delta R_{\rm stat}
  =R\sqrt{
    \left(\frac{\delta Y_{\rm data}}{Y_{\rm data}}\right)^2+
    \left(\frac{\delta Y_{\rm SIMC}}{Y_{\rm SIMC}}\right)^2}
  =0.663.
$$

Thus the toy result is `R = 1.30 +/- 0.66 (stat)`. A real analysis must also
propagate background-estimate uncertainty and correlated systematic
uncertainties; `sqrt(sum(fWeight^2))` alone is only the finite-SIMC-sample
component.

## 9. Data corrections versus effects modeled by SIMC

A practical separation is:

| Usually corrected or subtracted on data | Usually represented in SIMC/configuration |
|---|---|
| accumulated beam charge and charge calibration | charge-to-luminosity conversion |
| DAQ and electronic live time | generated phase-space volume |
| trigger efficiency | reaction cross-section model |
| tracking and detector efficiencies | spectrometer optics and apertures |
| PID efficiency and misidentification | multiple scattering and energy loss |
| random coincidences and target-wall backgrounds | internal/external radiation as configured |
| target boiling, if SIMC uses nominal density | particle decay or survival as configured |

This table is a default, not a substitute for reading a specific analysis.
For example, if a detector inefficiency is explicitly imposed in a custom
SIMC, applying it again to the data/SIMC ratio double counts it. Likewise,
one must decide whether target density is corrected in data or changed in
the SIMC input.

Radiative and bin-centering corrections require special care. In a direct
yield comparison, a radiated SIMC prediction should normally be compared to
radiated data; do not also "unradiate" the data unless the analysis is
explicitly extracting a Born-level result. Bin centering is often obtained
from the model after the yield comparison, rather than applied as an
ordinary detector efficiency.

## 10. Analysis recipe

For every data/SIMC comparison:

1. Define the reported quantity: corrected counts, counts/mC, or another
   explicitly luminosity-normalized yield.
2. Use matching run settings, target isotope and thickness, spectrometer
   settings, polarity, reaction channel, and radiation configuration.
3. Apply equivalent cuts to equivalent reconstructed variables. The
   `recon_hcana` output exists specifically to reduce differences between
   SIMC-style and hcana-style reconstructed physics variables.
4. Subtract data backgrounds and apply only the efficiencies absent from the
   simulation.
5. For positive-`Ngen` production SIMC, sum `fWeight` after the analysis cuts:

   ```cpp
   double y_simc = 0.0;
   double var_simc = 0.0;
   // for each entry passing the identical analysis/bin cuts:
   y_simc += fWeight;
   var_simc += fWeight * fWeight;
   ```

6. Match charge conventions: either rescale the SIMC sum to the data charge,
   or divide both results by their respective charges.
7. Compare both absolute normalization and distribution shapes.
8. Quote finite-data, finite-SIMC, background, efficiency, luminosity,
   acceptance/model, and other relevant uncertainties separately before
   forming the total.

## 11. Sanity checks

- **Charge scaling:** doubling `EXPER%charge` doubles `luminosity`, `normfac`,
  every `fWeight`, and the absolute SIMC yield. Dividing by charge removes
  that factor.
- **Monte Carlo convergence:** increasing positive `Ngen` ordinarily
  increases both `Ngen` and `Ntried`. The factor per event shrinks while more
  events are summed, leaving the expectation value unchanged and reducing
  statistical fluctuations.
- **Acceptance:** lower simulated acceptance increases `Ntried/Ngen`; failed
  throws contribute zero but remain represented by the `Ntried` denominator.
- **Raw `Weight`:** `sum(Weight)` lacks luminosity, generated volume, and the
  attempted-throw normalization, so it is not a predicted count.
- **Selected yield:** `sum(fWeight)` after a bin's cuts is the positive-
  `Ngen` SIMC prediction for that bin.
- **Cut equivalence:** matching cut names is insufficient if data and SIMC
  variables were reconstructed differently; compare definitions and units.
- **Special modes:** negative `ngen` and `doing_phsp` do not automatically
  obey the production `fWeight` workflow described here.

## 12. Compact answer to the six motivating questions

1. **Why compare yields?** Because both are estimates of the same accepted
   event-rate integral. Data measure it; SIMC integrates a model of it.
2. **What is a SIMC yield?** The sum of normalized event contributions. A
   charge of 1 mC is a convenient per-mC convention, not a simulated charge
   deposit and not an immutable SIMC assumption.
3. **What are `Ntried` and `Ngen`?** `Ntried` counts all random attempts.
   Positive `Ngen` requests that many successful events; negative `Ngen`
   requests that many attempts.
4. **What is `normfac`?** In normal positive-`Ngen` production,
   `luminosity * (Ngen/Ntried) * genvol`.
5. **What is `Weight`?** The event's differential physics integrand,
   including the configured cross section, Jacobian, generation correction,
   and applicable nuclear/target/survival factors.
6. **Why `Weight*normfac/Ngen`?** The `Ngen` cancels the success count inside
   `normfac`, leaving `Weight*luminosity*genvol/Ntried`, the standard Monte
   Carlo contribution. Summing that quantity—not taking one event's
   value—gives the SIMC yield.

## Source map for this repository

- `simc.f`: target/luminosity calculation, attempted-event loop, `Ngen`
  behavior, generation volume, and `normfac`.
- `event.f`: generated variables, event restrictions, Jacobians, cross-
  section completion, and construction of `main%weight`.
- `structures.inc`: definitions of `weight`, `gen_weight`, `jacobian`, charge,
  `ngen`, and `ntried`-related state.
- `infiles/*.inp`: user-facing `ngen`, `EXPER%charge`, target, kinematic, and
  acceptance inputs.
- `util/recon_hcana/recon_hcana.C`: construction of
  `fWeight = Weight*normfac/Ngen` for positive `Ngen`.

