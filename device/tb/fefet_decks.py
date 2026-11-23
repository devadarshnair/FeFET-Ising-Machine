"""Build ngspice decks for FeFET tests and read their results.

Three pieces:
  * MW-protocol decks: many FeFET instances, each with its own gate and drain source, run the
    protocol of device/tb/TESTS.md (+V, wait, -V, wait, read, +V, wait, read). All instances share
    the same read times, so one transient covers every (amplitude, width) point.
  * V_th extraction from the read ramps (constant-current criterion, log interpolation).
  * Snapshots: the full state of an instance (16 domain states and the internal node m) at one
    time. A new deck can start from a snapshot (x0_i parameters plus .ic on node m). This is used
    for long holds (retention), for reads after a hold, and to start TCAM searches from written cells.
"""
from pathlib import Path

import numpy as np

from checklib import REPO, read_wrdata

EDGE = 5e-9          # pulse rise and fall time
WAIT = 2.0           # wait between a write and the next read (s)
SLOT = 10.1e-3       # room for the longest pulse (10 ms) plus edges
V_DS_READ = 0.05     # drain voltage during reads
LIB = "../ngspice/fefet_preisach.lib"


class Protocol:
    """Shared times of the MW protocol. read_lo/read_hi: gate ramp range of the reads."""

    def __init__(self, read_lo, read_hi, ramp=26e-6, dv_point=0.02):
        self.read_lo, self.read_hi, self.ramp, self.dv_point = read_lo, read_hi, ramp, dv_point
        self.read_len = 1e-6 + ramp + 1e-6
        self.e1 = SLOT + 1e-6                    # end of pulse 1 (+V, conditioning)
        self.e2 = self.e1 + WAIT + SLOT          # end of pulse 2 (-V)
        self.r1 = self.e2 + WAIT                 # read 1 (high V_th) starts
        self.e3 = self.r1 + self.read_len + SLOT  # end of pulse 3 (+V)
        self.r2 = self.e3 + WAIT                 # read 2 (low V_th) starts
        self.t_end = self.r2 + self.read_len + 1e-6
        self.t_after_read1 = self.r1 + self.read_len + 0.5e-6
        # Snapshot times: 1 us BEFORE each read, because a read ramp that goes past V_th can
        # partly reprogram the cell (seen for set B: -64 mV on the high-V_th state).
        self.t_high = self.r1 - 1e-6     # high-V_th state, 2 s after the -V write
        self.t_low = self.r2 - 1e-6      # low-V_th state, 2 s after the last +V write

    def _pulse(self, end, amp, width):
        if amp == 0 or width <= 0:
            return []
        return [(end - width - 2 * EDGE, 0.0), (end - width - EDGE, amp), (end - EDGE, amp), (end, 0.0)]

    def _read(self, start):
        n = int(round((self.read_hi - self.read_lo) / self.dv_point))
        pts = [(start, 0.0)]
        for k in range(n + 1):
            pts.append((start + 1e-6 + self.ramp * k / n, self.read_lo + (self.read_hi - self.read_lo) * k / n))
        pts.append((start + self.read_len, 0.0))
        return pts

    def gate_points(self, amp, width, third_pulse=True):
        pts = [(0.0, 0.0)]
        pts += self._pulse(self.e1, +amp, width)
        pts += self._pulse(self.e2, -amp, width)
        pts += self._read(self.r1)
        if third_pulse:
            pts += self._pulse(self.e3, +amp, width)
        pts += self._read(self.r2)
        return pts

    def drain_points(self):
        pts = [(0.0, 0.0)]
        for r in (self.r1, self.r2):
            pts += [(r - 0.6e-6, 0.0), (r - 0.5e-6, V_DS_READ), (r + self.read_len + 0.1e-6, V_DS_READ),
                    (r + self.read_len + 0.2e-6, 0.0)]
        return pts

    def windows(self):
        """(start, stop) of the two gate ramps: read 1 = high V_th, read 2 = low V_th."""
        return [(r + 1e-6, r + 1e-6 + self.ramp) for r in (self.r1, self.r2)]


class ReadOnly(Protocol):
    """One read ramp starting at 1 us, for decks that start from a snapshot."""

    def __init__(self, read_lo, read_hi, ramp=26e-6, dv_point=0.02):
        super().__init__(read_lo, read_hi, ramp, dv_point)
        self.r1 = 1e-6
        self.t_end = self.r1 + self.read_len + 1e-6

    def gate_points(self, *_):
        return [(0.0, 0.0)] + self._read(self.r1)

    def drain_points(self):
        r = self.r1
        return [(0.0, 0.0), (r - 0.6e-6, 0.0), (r - 0.5e-6, V_DS_READ), (r + self.read_len + 0.1e-6, V_DS_READ),
                (r + self.read_len + 0.2e-6, 0.0)]

    def windows(self):
        return [(self.r1 + 1e-6, self.r1 + 1e-6 + self.ramp)]


def read_deck(title, comments, insts, prot, out_csv):
    """insts: [(name, subckt, snapshot)]. Each gets its own gate ramp and drain source."""
    lines = deck_header(title, comments)
    vecs = []
    for name, subckt, snap in insts:
        lines.append(pwl(f"Vg_{name}", f"g_{name}", prot.gate_points()))
        lines.append(pwl(f"Vd_{name}", f"d_{name}", prot.drain_points()))
        lines.append(instance_from_snapshot(f"X{name}", f"g_{name} d_{name} 0 0", subckt, snap))
        vecs += [f"v(g_{name})", f"i(vd_{name})"]
    lines += control_block(prot.t_end, out_csv, vecs)
    return "\n".join(lines) + "\n"


def pwl(name, node, points, per_line=6):
    """A PWL voltage source; points with equal times are nudged forward by 1 ps."""
    out, last = [], -1.0
    for t, v in points:
        t = max(t, last + 1e-12)
        out.append(f"{t:.12g} {v:.6g}")
        last = t
    lines = [f"{name} {node} 0 pwl("]
    for k in range(0, len(out), per_line):
        lines.append("+ " + " ".join(out[k:k + per_line]))
    lines[-1] += ")"
    return "\n".join(lines)


def deck_header(title, comment_lines):
    head = [f"* {title}"] + [f"* {c}" for c in comment_lines]
    head += [f".include {LIB}", ".options reltol=1e-4 abstol=1e-15 method=gear"]
    return head


def mw_deck(title, comments, subckt, points, prot, out_csv, third_pulse=True, inst_params=""):
    """Deck with one FeFET per (amp, width) point running the full MW protocol."""
    lines = deck_header(title, comments)
    vecs = []
    for k, (amp, width) in enumerate(points):
        lines.append(pwl(f"Vg{k}", f"g{k}", prot.gate_points(amp, width, third_pulse)))
        lines.append(pwl(f"Vd{k}", f"d{k}", prot.drain_points()))
        lines.append(f"X{k} g{k} d{k} 0 0 {subckt} {inst_params}".rstrip())
        vecs += [f"v(g{k})", f"i(vd{k})"]
    lines += control_block(prot.t_end, out_csv, vecs)
    return "\n".join(lines) + "\n"


def control_block(t_end, out_csv, vecs, tmax=None, extra_csv=None, extra_vecs=None):
    """Without an explicit max step ngspice limits the step to tstep (1 ns here), which makes a
    6 s protocol take hours. Default max step: t_end / 200."""
    tmax = tmax or t_end / 200
    tm = f" 0 {tmax:.6g}"
    lines = [".control", "set wr_singlescale", "set wr_vecnames", f"tran 1n {t_end:.12g}{tm} uic"]
    lines.append(wrap_cmd(f"wrdata {out_csv}", vecs))
    if extra_csv:
        lines.append(wrap_cmd(f"wrdata {extra_csv}", extra_vecs))
    lines += [".endc", ".end"]
    return lines


def wrap_cmd(head, items, per_line=8):
    out = [head + " " + " ".join(items[:per_line])]
    for k in range(per_line, len(items), per_line):
        out.append("+ " + " ".join(items[k:k + per_line]))
    return "\n".join(out)


def state_vectors(inst, n=16):
    return [f"v({inst}.xfe.x{i})" for i in range(1, n + 1)] + [f"v({inst}.m)"]


def vth_from_ramp(t, vg, i_vsrc, window, i_crit):
    """Gate voltage where the drain current first rises through i_crit inside the ramp window."""
    k = (t >= window[0]) & (t <= window[1])
    v, i = vg[k], np.maximum(-i_vsrc[k], 1e-30)
    li = np.log(i)
    above = np.where(li >= np.log(i_crit))[0]
    if len(above) == 0 or above[0] == 0:
        return float("nan")
    j = above[0]
    f = (np.log(i_crit) - li[j - 1]) / (li[j] - li[j - 1])
    return float(v[j - 1] + f * (v[j] - v[j - 1]))


def mw_results(csv_path, prot, n_points, i_crit):
    """[(vth_low, vth_high), ...] per instance from an mw_deck run."""
    d = read_wrdata(csv_path)
    t = d["time"]
    w_hi, w_lo = prot.windows()
    res = []
    for k in range(n_points):
        vg, idd = d[f"v(g{k})"], d[f"i(vd{k})"]
        res.append((vth_from_ramp(t, vg, idd, w_lo, i_crit), vth_from_ramp(t, vg, idd, w_hi, i_crit)))
    return res


def snapshot(data, inst, time, n=16):
    """State of one instance at one time from a wrdata dict: {'x': [n], 'vm': float}."""
    t = data["time"]
    x = [float(np.interp(time, t, data[f"v({inst}.xfe.x{i})"])) for i in range(1, n + 1)]
    return {"x": x, "vm": float(np.interp(time, t, data[f"v({inst}.m)"]))}


def instance_from_snapshot(name, nodes, subckt, snap, extra=""):
    """Instance line plus its .ic line, starting from a snapshot."""
    items = [f"x0_{i}={v:.9g}" for i, v in enumerate(snap["x"], 1)] + extra.split()
    line = wrap_cmd(f"{name} {nodes} {subckt}", items, per_line=6)
    return line + f"\n.ic v({name.lower()}.m)={snap['vm']:.9g}"


def write(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def rel(path):
    return str(Path(path).resolve().relative_to(REPO))
