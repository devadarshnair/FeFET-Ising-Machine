# Hardware phase (hw/) layout
- docs/hw/TOOLS.md: tool versions, sources, licences, install log.
- docs/hw/lit/: literature extraction notes (Yin 2024, BFE-CiM 2512.17165, Aramon 2019, HyCiM D-QUBO).
- docs/hw/results/: small per-task result summaries (<task-id>.md); bulk output stays in sim/out/hw/.
- - prereg/calib/: calibration tolerance files, committed untagged before checks; prereg/drafts/: DRAFT preregs.
- scripts/golden, scripts/baselines, scripts/problems: golden/cost model, baseline machines, problem mappings.
- tests/hw/: pytest; rtl/cfg, rtl/verilator, rtl/synth: RTL configs, Verilator target, Yosys flow.
- circuit/cim/: crossbar and ADC circuits; models/mosfet/: FreePDK45 and PTM45 cards.
- 