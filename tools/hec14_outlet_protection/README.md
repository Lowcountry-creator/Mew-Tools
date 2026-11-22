# HEC-14 Culvert Outlet Protection

Python port of the Outlet Protection Calcs workbook (FHWA HEC-14 3rd ed.
Chapter 10 with HY-8). Same ten blocks, same formulas, same limits, same
result wording, so a run can be checked line by line against the spreadsheet
or the HY-8 Riprap Basin printout.

Standard library only. Python 3.8+.

## Run

```bash
# Built-in worked example (US176 Culvert 1)
python hec14_outlet_protection.py --example culv1

# Your culvert
python hec14_outlet_protection.py --template > culv.json   # edit the inputs
python hec14_outlet_protection.py culv.json --out culv_report.txt --json-out culv.json.out

# Tests
python -m pytest
```

Or import it:

```python
from hec14_outlet_protection import Inputs, analyze, format_report
r = analyze(Inputs(Q=639.56, Wo=14, rise=7, embedment=1, yo=2.8, Vo=16.32,
                   TW=5.14, V_channel=7.02, slope=0.0211,
                   V_LB=[11.741, 6.235, 4.145, 3.102], HS_hy8=1.819))
print(r.trial_gives, r.L_adopted, r.option_1)
```

## Inputs (block 1)

| Key | Units | Source |
|---|---|---|
| `Q` | cfs | HY-8 Culvert Summary Table, design storm row |
| `yo`, `Vo`, `TW`, `V_channel` | ft, fps, ft, fps | Same row: Outlet Depth, Outlet Velocity, Tailwater Depth, Tailwater Velocity |
| `Wo`, `rise`, `embedment` | ft | Plans. `Wo` is the total clear width, all barrels |
| `slope` | ft/ft | HY-8 Tailwater Data. `null` skips the block 9 shear check |
| `V_perm`, `tau_perm` | fps, psf | SCDOT Stormwater Quality Design Manual App. E, Tables E.2 and E.3 |
| `Ss` | | Riprap specific gravity, 2.65 default |
| `D50_trial`, `min_class` | ft, A to D | Stone run in HY-8; smallest class the Engineer will call out |
| `V_LB` | fps, 4 values | HY-8 Riprap Basin, Downstream Riprap for High TW, jet velocity at 1 to 4 LB |
| `HS_hy8` | ft | HY-8 Pool Depth (HS), Envelope Curve. Optional, ties the run to the printout |

`LB` is computed (4 Wo with no pool; Ls + La with one) and should match the
HY-8 Basin Length.

## What each block does

1. Inputs.
2. Outlet hydraulics: D, yc, regime, Vo check, ye = yo, Fr, TW/ye.
3. Applicability screen, HEC-14 Table 1.1 (apron rise <= 60 in; basin Fr < 3; jump basin Fr >= 1.7).
4. Riprap basin check, Eq. 10.1: hs/ye = 0.86 (D50/ye)^-0.55 Fr - C0, with C0 from the Envelope Curve (Eq. 10.2, design) and Best Fit (Eq. 10.3, comparison). Valid basin needs 0.1 <= D50/ye <= 0.7, hs > 0, hs/D50 >= 2. Run for the trial stone and SCDOT Classes A to D.
5. Basin geometry when the trial stone gives a basin: Ls = max(10 hs, 3 Wo), La = max(5 hs, Wo), width Wo + 2/3 (Ls + La), thickness 3 D50 approach and 2 D50 pool and apron.
6. Velocity decay from the HY-8 jet velocities at 1 to 4 LB.
7. Protection length: target is the larger of permissible velocity and channel velocity; length by linear interpolation between the HY-8 points, not less than 1 LB, rounded up to 6 ft. High tailwater (TW/ye > 0.75) only.
8. Riprap sizing, Eq. 10.6: D50 = 0.692 V^2 / (2 g (Ss - 1)) per reach; class is the smallest SCDOT class meeting it, not less than `min_class`. Headwall class for a lined channel also takes the smallest class with no scour pool.
9. Receiving channel, HEC-15 shear basis: tau = gamma TW S against `tau_perm`; bed D50 = tau / (0.047 (Ss - 1) gamma) when exceeded.
10. Design summary: Option 1 lined channel, Option 2 riprap basin, length, vertical limits, banks, basis.

## Reading the result

- `Lined channel, no pool`: HY-8 shows HS = 0.000 and a red HS/D50. Expected, not an error.
- `Riprap basin (Sec 10.1)`: block 5 gives the pool and apron.
- `Change trial D50`: the stone is out of range or gives a shallow pool. Use `largest_valid_class` and `smallest_no_pool_class` to pick a class, rerun HY-8, update the inputs.

## Verification

`test_hec14_outlet_protection.py` checks every computed cell of the three
US176 culvert tabs (Culverts 1, 2 and 4) to 1e-9, plus branch coverage for
the C0 curves, the Excel CEILING rounding, interpolation past 4 LB, class
selection, the low tailwater path and input validation.

## Known limits

- Rectangular (box) outlets only: ye = yo. Circular or pipe arch outlets need
  ye = (A/2)^0.5 per HEC-14 Sec 10.1, which this port does not yet do, same as
  the workbook.
- The Sec 10.2 riprap apron method (Eq. 10.4 and 10.5) is screened for
  applicability but not computed, same as the workbook.
- SCDOT class table is hard coded. Edit `SCDOT_CLASSES` for another DOT.

## Basis

HEC-14 3rd ed. (FHWA-NHI-06-086) Table 1.1, Sec 10.1, 10.1.3, 10.3; HEC-15
3rd ed.; HY-8 Energy Dissipation report (Riprap Basin, Envelope Curve); SCDOT
Stormwater Quality Design Manual App. E Tables E.2 and E.3; SCDOT Std Spec
Sec 804.
