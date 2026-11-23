# S2 prereg, amendment 1 (errata). Written 22 Nov 2026 after Stage 2

This amendment does not edit `prereg/hw/S2_confirmatory.md`, which stays frozen. It records two text corrections, DOC-1 and DOC-2 in
`docs/hw/diagnosis/FIX_LEDGER.md`. Neither changes the frozen decision rule, the evaluator, the instances, the arms or any verdict in
`docs/hw/diagnosis/STAGE2_RESULTS.md`.

## A1.1 (DOC-1): restart-block share in section 1, line 8
- **Frozen text:** "The kick itself is not the cost (restart block 0.09 % of ours' energy)".
- **Error:** 0.09 % is the restart block as stored in the Stage 1b records, which were priced with the frozen cost table. Under the primary
  `measured_v2` pricing, the restart block is about 8 % of ours' energy for both ours_new and ours_h8. That share is the restart unit's own
  idle and leakage cost and does not grow with the number of kicks, so it says nothing about the energy of the kicks themselves.
- **Direct measure (STAGE2_RESULTS section 5.1):** ours_new makes about 5x more kicks than ours_h8 and costs +1.6 % energy per run at
  p3n480 ideal.
- **Conclusion:** "the kick is not the cost" still holds, but on the +1.6 % measure, not on the 0.09 % figure.
- **Where else it appears:** the same number is in `STAGE1B_RETUNE.md` line 19, which now carries an erratum note pointing here.

## A1.2 (DOC-2): loss wording vs the evaluator class
- **Governing loss rule (as implemented):** `evaluate_s2.py` uses the H8 class `evalcommon.energy_verdict`. A contrast is a **loss** when the
  ETS99 ratio is >= 1.0 **and** the 95 % bootstrap CI lower bound is > 1.0. No Holm adjustment is applied to a loss.
  A **win** needs all of: ratio <= 0.95, Holm p < 0.05, CI upper bound < 1, and success not worse than -1 pp.
- **Superseded wording:** the earlier draft falsifier ("ratio >= 1.05 with its Holm-adjusted lower bound above 1", draft section 1) and the
  frozen header sentence "where the loss-condition wording here differs ... the evaluator governs" both refer to this rule. The rule
  above is the one that was applied, before and after the data.
- **Interpretation:** a contrast that meets neither condition is "inconclusive", read as "no energy advantage shown" (frozen section 1).

## A1.3: a post-hoc reading that does not replace the frozen one (EVAL-1)
- **Frozen reading:** a comparator with 0 % success (ETS = inf) gives ratio 0, which the frozen class labels a "win". This affects
  p4n480 and p4n240 vs B3_h8. Neither is a decision cell.
- **H8 convention:** such a contrast is "not evaluable", i.e. a success win, not an energy win.
- **Post-hoc option:** `evaluate_s2.py --eval1` (default off) prints this reading next to the frozen one. The frozen verdicts stand.
