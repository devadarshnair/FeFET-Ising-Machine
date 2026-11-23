# Tool manifest (hardware phase)

Recorded 15 Nov 2026, IST. Add to PATH: `export PATH=$HOME/tools/verilator/bin:$HOME/tools/yosys/bin:$HOME/tools/openvaf:$PATH`.
Downloaded code policy: tools are built/installed only; downloaded research code is never executed.

## Verilator (P0.02)
- Version: `Verilator 5.050 2026-07-01 rev v5.050`. Location `$HOME/tools/verilator/` (user space, no sudo).
- Provenance: already present on this machine (installed 21 Sep 2026 for another project; binary mtime 21 Sep 12:17). Reused instead of
  reinstalling; the original source URL/tarball SHA was not recorded at install time. `verilator_bin` SHA-256
  `40a25f2221a514b53ccf4f1ca459f3b9f3060cb0bafd1d8b8f41016664c90586`.
- Licence: LGPL-3.0-only OR Artistic-2.0.
- Acceptance: `verilator --lint-only -Wall rtl/src/xoshiro128ss.v` rc 0 (log `sim/out/hw/p0/verilator_lint.log`).

## Yosys (P0.03)
- Version: `Yosys 0.69 (git sha1 9f75ca1f9, Release, GNU /usr/bin/c++ 11.4.0)`. Location `$HOME/tools/yosys/`.
- Provenance: pre-existing user-space install (21 Sep 2026, other project); source URL not recorded. `yosys` SHA-256
  `9011c9eb6af6df71dcedd4b8a35c4ffc28d882ac224907978e2fcea0380493bb`.
- Licence: ISC.
- Acceptance: `yosys -p "read_verilog rtl/src/seg_adder.v; synth; stat"` rc 0 (default NSEG=1 is a plain copy, 0 logic cells;
  log `sim/out/hw/p0/yosys_segadder.log`). With NSEG=4: 5478 generic cells (`yosys_segadder_nseg4.log`), so the count path works.

## OpenVAF-reloaded (P0.04)
- Version: `OpenVAF-reloaded 20260616-3-g0e83f1ed`. Binary `$HOME/tools/openvaf/openvaf` (SHA-256
  `b117284d8f871dbf54609ab009cdff819f443d8d33064111b8b0782af5c7e931`).
- Source: https://fides.fe.uni-lj.si/openvaf/download/openvaf-reloaded-20260616-3-g0e83f1ed-linux_x64.tar.gz (tarball SHA-256
  `82ce7587c7e5f54faac997aefb91de99a30a6d2ac4eb6bd2dbbff17ddcd1b1a3`, downloaded 15 Nov 2026). Newer 0.5-OSDI builds exist on that page and
  were not used because ngspice 45.2 compatibility with OSDI 0.5 is unchecked; this build loads in ngspice 45.2.
- Licence: GPL-3.0 (as stated in IMPL_PLAN; no licence file shipped in the tarball). Only the binary was run, with `--version`, `--help` and on our own `.va`.
- Check: `sim/out/hw/p0/res.va` (5-line resistor, R=500) compiled to `res.osdi`, loaded by `pre_osdi`, `.op` at 2 V gives
  `i(v1) = -4.00000e-03` A = V/R exactly (sign: current into the source). Deck `sim/out/hw/p0/osdi_res.cir` is committed (force-added; `sim/out/` is ignored) and is run from the worktree root.
- ngspice-45.2 in use (`/usr/bin/ngspice`).

## Other tools in the flow (P0.06, 15 Nov 2026 IST)
| Tool | Version | Path / note |
|---|---|---|
| ngspice | 45.2 (KLU) | `/usr/bin/ngspice` (system, Sep 2025) |
| Icarus Verilog | 12.0 (stable) | system `iverilog`/`vvp` |
| Verilator | 5.050 2026-07-01 | `~/tools/verilator/bin` |
| Yosys | 0.69 (9f75ca1f9) | `~/tools/yosys/bin` |
| OpenVAF-reloaded | 20260616-3-g0e83f1ed | `~/tools/openvaf/openvaf` |
| Python (runner env `swref`) | 3.12.15, numpy 2.3.5, scipy 1.18.1 | `$HOME/miniconda3/envs/swref/bin/python` (both runners use it) |
| Python (system/miniconda base) | 3.13.13 | not used by the runners |

MOSFET cards: FreePDK45 NCSU nominal (Apache-2.0) and PTM 45 nm HP/LP: see `models/mosfet/{freepdk45,ptm45}/SOURCE.md` and `CARD_CHOICE.md`.

## Baseline re-run on the unchanged v0 runners (P0.06)
Logs `sim/out/hw/P0.06/` (uncommitted). Runs on branch `hw/p0-setup` at the P0.05 commit, no code changes since `main` `0ab5e5c`.
- `scripts/run_rtl_tests.sh` (default, long runs skipped): 23 tests, 23 PASS. `--long`: 24 tests, 24 PASS (matches the 24/24 of `docs/rtl/STATUS.md`).
- `scripts/run_spice_tests.sh all`: **31 tests, 18 PASS, 13 FAIL**, ids and verdicts identical to the table in `docs/device/STATUS.md`
  (compared programmatically; STATUS marks two ids with "(added)"). Wall time about 33 min.
- The runner reports "broken steps 25": all 25 are the t3d Monte Carlo decks (`sim/out/t3d/t3d_mc000..024.cir`), flagged because ngspice prints
  `Error: measure tdN trig(TARG) out of interval` for samples whose delay never crosses the trigger (the v0 `t3d.levels` test fails by reading only 1 level).
  The checker still produced its result and the pass/fail table is unchanged. STATUS.md recorded "0 broken steps" for the earlier waveform-file
  decks; the measure-only decks (changed after that run) trip the runner's `^error` grep. This is a runner false positive, not a regression in a verdict;
  it is left unfixed here (runners must stay unchanged for P0.06) and is carried to P1.09 (t3d.levels), where those decks are touched anyway.
