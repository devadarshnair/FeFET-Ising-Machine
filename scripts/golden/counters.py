"""Op counters and cycle model of the golden machine (P2.06). Feeds the cost model (P2.07).

Counted once per machine step (n = lanes, m = constraint rows, w = CiM weight bits, cols = 2*w*n columns:
w planes x 2 polarities per lane):
  field_reads         field reads actually performed (any path)        skipped_reads   I10-skipped reads (cache used)
  array_reads         CiM array reads (one per performed read, CiM path only)
  array_cell_reads    rows x cols activated per array read = n * cols
  adc_conversions     cols per array read;  adc_conv_bits = conversions x bits at the bits used
  adc_lowbit_conv     I7 low-bit conversions: conversions made with bits < the nominal CiM bits (cfg.adc_bits);
                      adc_lowbit_bits = their conversions x bits.  Counted separately from skipped reads.
  adds                shift-add 2w per lane per array read; acceptance 2 per lane per step; h update n per flip
  rng_draws           n lane draws + 1 selection draw per step + L kick draws per kc2 restart
  lut_reads           n per step
  reg_writes          step counter 1; T 1 if geometric; E_off 1; per flip: x 1, h n, f 1, loads m (knapsack);
                      best 1 on improvement; restart reload: x n, h n, f 1, loads m, +T, +E_off for mesa/kc2_reset
  array_writes        TCAM-lite row writes
  tcam_searches       TCAM-lite visited-state searches + 2 pricer searches per step in knapsack "hw" rule
  restarts            restart events
  best_updates        best-so-far improvements (MESA writes its n-bit best-state shadow register on each)
  gated_cycles        steps whose ADC bias is gated by I10 (power.bias_gated delta)
  ramp_updates        I3 penalty-ramp register updates (steps with t <= ramp_steps)
  vth_samples         I5 device (Vth-spread) noise samples taken (replace digital lane RNG draws)
I11 (greedy): no lane RNG draws (rng_draws = 1 selection draw + L per kick), no LUT reads, no T / E_off register writes.
I5: rng_draws = 1 selection draw (+ L per kick) and no LUT reads; the lane noise is counted in vth_samples instead.
`restart_cycles` (kept apart from `cycles`, which is the per-step state machine; the RTL exports it as rs_cycles): cycles spent in S_RST by the restarts of the step.
Cycles per step: SPEC_v0 section 4 (QUBO 3 + sel_lat = 4; knapsack 6 + sel_lat + 2*search_lat = 7 + 2*search_lat) plus, per performed CiM read,
cim_array_lat + bits (array settle, then a b-cycle SAR conversion with all columns in parallel); skipped reads add
none; plus 1 cycle per TCAM-lite search.
"""
from __future__ import annotations

from dataclasses import dataclass, field

FIELDS = ("field_reads", "skipped_reads", "array_reads", "array_cell_reads", "adc_conversions", "adc_conv_bits",
          "adc_lowbit_conv", "adc_lowbit_bits", "adds", "rng_draws", "lut_reads", "reg_writes", "array_writes",
          "tcam_searches", "restarts", "gated_cycles", "best_updates", "ramp_updates", "vth_samples", "restart_cycles", "cycles")


@dataclass
class CycleCfg:
    search_lat: int = 2      # SPEC_v0 SEARCH_LAT
    cim_array_lat: int = 1   # array settle cycles per performed CiM read
    sel_lat: int = 1         # cycles in state SEL (pipelined select tree, timing study v2); 1 = the single-cycle tree of v0.
                             # Only the cycle count changes: the selected spin of every step is identical


class OpCounters:
    def __init__(self, cfg: CycleCfg | None = None):
        self.cfg = cfg or CycleCfg()
        self.total = dict.fromkeys(FIELDS, 0)
        self.steps: list[dict] = []
        self._tc = (0, 0)
        self._gated = 0
        self._tw = (0, 0)

    def record(self, m, *, k: int, performed: bool, bits: int | None, restarted: bool, improved: bool) -> None:
        inst, c = m.inst, {f: 0 for f in FIELDS}
        n, mm = inst.n, inst.m if m.knap else 0
        if performed:
            c["field_reads"] = 1
            if m.cim is not None:
                w = m.cim.cfg.w_bits
                cols = 2 * w * n
                c["array_reads"] = 1
                c["array_cell_reads"] = n * cols
                c["adc_conversions"] = cols
                c["adc_conv_bits"] = cols * bits
                c["adds"] += 2 * w * n
                if bits < m.cim.cfg.adc_bits:
                    c["adc_lowbit_conv"] = cols
                    c["adc_lowbit_bits"] = cols * bits
                c["cycles"] += self.cfg.cim_array_lat + bits
        else:
            c["skipped_reads"] = 1
        c["adds"] += 2 * n
        tw = m.tw
        lane_noise = tw is None or tw.lane_noise
        c["rng_draws"] = n + 1 if lane_noise else 1
        c["lut_reads"] = n if lane_noise else 0
        regs = 1 if m.greedy else 1 + (1 if inst.geom else 0) + 1
        if tw is not None:
            c["ramp_updates"] = tw.ramp_updates - self._tw[0]
            c["vth_samples"] = tw.samples - self._tw[1]
            self._tw = (tw.ramp_updates, tw.samples)
            regs += c["ramp_updates"]
        if k >= 0:
            c["adds"] += n
            regs += 1 + n + 1 + mm
        if improved:
            regs += 1
            c["best_updates"] = 1
        if restarted:
            c["restarts"] = 1
            c["restart_cycles"] = m.restart.last_cycles
            regs += 2 * n + 1 + mm
            if m.restart.cfg.arm == "kc2":
                c["rng_draws"] += m.restart.L
            if m.restart.cfg.arm == "mesa" or m.restart.cfg.kc2_reset_sched:
                regs += 2
        c["reg_writes"] = regs
        if m.tcam is not None:
            ts, tw = m.tcam.searches, m.tcam.writes
            c["tcam_searches"] = ts - self._tc[0]
            c["array_writes"] = tw - self._tc[1]
            c["cycles"] += c["tcam_searches"]
            self._tc = (ts, tw)
        if m.rows is not None:
            c["tcam_searches"] += 2
        if m.power is not None:
            c["gated_cycles"] = m.power.bias_gated - self._gated
            self._gated = m.power.bias_gated
        base = 6 + self.cfg.sel_lat + 2 * self.cfg.search_lat if m.knap else 3 + self.cfg.sel_lat
        c["cycles"] += base
        self.steps.append(c)
        for f in FIELDS:
            self.total[f] += c[f]
