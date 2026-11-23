# Amendment 1 to the Stage 3.2 prereg (`S3_confirmatory.md`, frozen at fd87994): erratum on T-5. Dated 2026-11-23.

The frozen prereg is **not edited**. This amendment adds a caveat on interpretation after the fact. It changes no registered analysis, rule or verdict.

## Erratum
- The registered Stage 3.2 primary pricing for ours_stack is `all,b3b,t1f,t5,t6` (`scripts/testing/evaluate_s3.py:32`). It includes **T-5**, which overlaps the per-update read (settle + 1-bit sense, 2 cycles) with the select tree.
- Round 3 found that T-5 cannot be built causally. Under T-1 the row to read is the spin k selected by S_SEL in the same step, and the next S_ACC needs the updated field. The chain read → UPD → ACC → SEL (`rtl/src/tim_ctrl.v:74-76`, FSM transitions) is therefore a true dependency loop.
  Speculation does not rescue it: the hit rate is about 1/c, and the replay costs the cycles back.
  Sources: the round-3 design notes §2.2 (5d8b127) and the engineering notes §14.1 (eaeb724).
- The registered pricing therefore credits ours with about 2 cycles per update that real hardware would not save. That is about x1.25 on ours' energy per run (`r3_a_evidence/term_sens.txt`).

## Stage 3.2 verdicts re-priced without T-5 (EXPLORATORY, not registered; same records, same rule, B = 2000)
ETS99 ratio ours_stack / B3 (below 1 favours ours). Sources: `docs/hw/diagnosis/s3_reprice_v3.md` and `s3_reprice_v4.md` (the engineering notes §14-15).

| cell | **registered** (estimates + T-5) | measured_v3 (synthesised T-1 digital, no T-5, k 0) | measured_v4 candidate (m3 + OpenRAM/CACTI SRAMs, no T-5, SRAM table k 64, gating split) |
|---|---|---|---|
| p3n480 vs B3_sel / B3_h8 | 0.50 win / 0.54 inconclusive → NO ADVANTAGE SHOWN | 0.61 / 0.66 → NO ADVANTAGE SHOWN | 0.75 / 0.81 (both inconclusive) → NO ADVANTAGE SHOWN |
| p4n480 vs B3_sel (B3_h8 at 0 % success) | 0.43 → **SUPPORTED** | 0.53 → SUPPORTED | 0.65 [0.43, 0.88] → SUPPORTED |
| p3n960 vs B3_sel / B3_h8 | 1.22 / 1.49 → NO ADVANTAGE SHOWN | 1.50 / 1.84 loss → FALSIFIED | 1.78 / 2.18 loss → FALSIFIED |
| Max-Cut vs B3_sel / B3_h8 | 13.2 / 9.1 → FALSIFIED | 16.4 / 11.4 → FALSIFIED | 19.6 / 13.5 → FALSIFIED |

Under measured_v4 without T-5, p4n480 is **no longer** supported if any one of the following holds (`s3_reprice_v4.md`):
- B3's SRAM read at x0.5 (0.70);
- B3's RNG at x0.5 (0.71);
- analog estimates at x2 (0.71, so the registered "x2" condition would fail);
- full gating on both machines (0.73).

## Citation rule
The registered p4n480 **SUPPORTED** stands as the registered outcome. It may be cited **only** together with this caveat:
"Registered pricing included a read/select overlap (T-5) later found causally unbuildable. Without it, the exploratory re-pricing still gives p4n480 0.53-0.65, but the result no longer survives x2 analog estimates or x0.5 on B3's SRAM or RNG energy."
p3n960 should be reported as a loss (FALSIFIED) under any T-5-free pricing.
