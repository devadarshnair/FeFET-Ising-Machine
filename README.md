# FeFET Compute-in-Memory Ising Machine

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![NumPy](https://img.shields.io/badge/NumPy-013243?logo=numpy&logoColor=white)
![Numba](https://img.shields.io/badge/Numba-00A3E0?logo=numba&logoColor=white)
![pytest](https://img.shields.io/badge/pytest-0A9EDC?logo=pytest&logoColor=white)
![Verilog](https://img.shields.io/badge/Verilog-RTL-8A2BE2)
![Verilator](https://img.shields.io/badge/Verilator-lint%20%2B%20sim-FF6F00)
![Icarus Verilog](https://img.shields.io/badge/Icarus%20Verilog-sim-6E4C13)
![Yosys](https://img.shields.io/badge/Yosys-synthesis-2E8B57)
![OpenROAD](https://img.shields.io/badge/OpenROAD-place%20%26%20route-1F6FEB)
![Nangate45](https://img.shields.io/badge/Nangate45%20%2F%20FreePDK45-45%20nm-555555)
![OpenRAM](https://img.shields.io/badge/OpenRAM-SRAM%20characterisation-C71585)
![CACTI](https://img.shields.io/badge/CACTI%207-memory%20model-B22222)
![ngspice](https://img.shields.io/badge/ngspice-SPICE-0B7285)
![Verilog-A](https://img.shields.io/badge/Verilog--A-FeFET%20model-DAA520)

An Ising / QUBO solver built on a FeFET compute-in-memory (CiM) array, designed from the device up and compared,
on one shared device, circuit and cost model, against a FeFET simulated-annealing machine (Yin et al. 2024),
HyCiM, and a Fujitsu Digital Annealer–style digital baseline.

The machine computes local fields inside a multi-level FeFET crossbar and uses **greedy, temperature-free
acceptance** (no RNG, no lookup table) with a **stall-triggered kick** to escape local minima.

## Headline results
All confirmatory results come from experiments pre-registered (frozen by commit) before any data existed.
Energies come from a cost model built from Yosys/OpenROAD synthesis on Nangate45, OpenRAM/CACTI SRAM
characterisation and SPICE device models. They are model results, not silicon.

| Comparison | Result |
|---|---|
| vs FeFET SA machine (Yin et al. 2024) | ~24× lower energy-to-solution, far higher success (480 spins) |
| vs DA-style digital annealer, 4-colouring, 480 spins | ~0.65× energy-to-solution (supported, sensitive to SRAM assumptions) |
| vs DA-style annealer, 3-colouring, 480 spins | ~0.75× energy, success bound not met (no advantage shown) |
| Structured (DIMACS-style) colouring, earlier design | ~100× lower energy |
| 960 spins, Max-Cut | DA-style annealer wins (stated limitations) |
| Device variation | per-cell leakage screening + correction table keeps ideal success across the estimated FeFET variation range |

Details, caveats and errata: `docs/hw/results/` and `docs/hw/diagnosis/STAGE*_RESULTS.md`.

## Repository layout
- `device/` – FeFET compact model (Preisach polarisation, switching dynamics) in Verilog-A and ngspice form.
- `circuit/` – CiM / TCAM cells and arrays at transistor level, with ngspice testbenches.
- `models/` – MOSFET model cards.
- `rtl/` – Verilog of the machine (field unit, pipelined select tree, restart unit, control), synthesis and place-and-route flow.
- `scripts/golden/` – bit-exact golden model of the machine.
- `scripts/baselines/` – baseline machines (Yin MESA, HyCiM, DA-style annealer).
- `scripts/problems/` – problem generators (graph colouring, Max-Cut, DIMACS-style families).
- `scripts/testing/` – experiment runners, variation model, cost model and evaluators.
- `scripts/cloud/` – one-command batch runners used for the large runs.
- `prereg/` – frozen pre-registrations and amendments.
- `tests/` – unit, regression and RTL ↔ golden equivalence tests.
- `docs/` – results, analyses, literature notes and RTL specification.

## Running the tests
```bash
python -m pytest -q tests/hw
```

## Method
- Pre-register before every confirmatory run; report every outcome, including failures and errata.
- Same device model, MOSFET model, cost model and tuning effort for every machine.
- Holm-corrected comparisons with bootstrap confidence intervals on energy-to-solution.
