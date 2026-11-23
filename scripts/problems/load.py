"""P5.04: one problem interface for every machine.

load_* builds ONE MappedQubo (integer d, symmetric P, constant offset, optional knapsack row) per problem; its SHA-256
covers the mapped integers only. machine_configs() wraps that single object for ours (I7/I10 + restart arms), B1 Yin
MESA, B2 HyCiM and B3 Fujitsu DA. Each config records the scale/quantisation to its coupling bits and the loss; the
mapped hash and the spin count are identical across machines by construction (PLAN fairness).

Convention (golden tim_golden.objective): f(x) = d.x + x^T P x / 2 = sum_i d_i x_i + sum_{i<j} P_ij x_i x_j + offset,
minimised. Max-Cut: f = -cut. MaxSAT: f = violated weight. Colouring: f = penalty energy.
CLI: `python -m scripts.problems.load` writes docs/hw/results/P5.04_quant_loss.csv.
"""
from __future__ import annotations

import csv
import hashlib
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
for _sub in ("scripts/golden", "scripts/baselines"):
    if str(REPO / _sub) not in sys.path:
        sys.path.insert(0, str(REPO / _sub))

from tim_golden import D_MAX, D_MIN, P_MAX, P_MIN  # noqa: E402

from . import maxcut as mc  # noqa: E402
from . import spin_table as st  # noqa: E402

OUT_CSV = REPO / "docs" / "hw" / "results" / "P5.04_quant_loss.csv"
OURS_MAX_SPINS = st.OURS_SPINS
LOSS_STATES = 200
LOSS_SEED = 20261115


@dataclass(frozen=True)
class Quantiser:
    """Signed integer ranges [p_lo, p_hi] for couplings, [d_lo, d_hi] for biases; None = unquantised (digital)."""
    p_range: tuple[int, int] | None
    d_range: tuple[int, int] | None
    note: str


QUANT = {
    "ours": Quantiser((P_MIN, P_MAX), (D_MIN, D_MAX), "10-bit couplings, 12-bit biases (tim_golden P_BITS/D_BITS)"),
    "b1": Quantiser((-7, 7), None, "Yin 3-bit magnitude per polarity (|P|<=7); bias digital"),
    "b2": Quantiser(None, None, "HyCiM profit matrix in digital periphery; only knapsack weights go to the array"),
    "b3": Quantiser((-(1 << 15), (1 << 15) - 1), (-(1 << 25), (1 << 25) - 1), "Fujitsu DA 16-bit couplings, 26-bit bias"),
}
ARMS = {
    "ours": ("none", "da_offset", "kc2"),  # I7 + I10 on, restart arm selects golden restart.py arm
    "b1": ("mesa",),
    "b2": ("hycim",),
    "b3": ("da_offset",),
}


@dataclass(frozen=True)
class MappedQubo:
    name: str
    family: str
    d: np.ndarray            # (n,) int64
    P: np.ndarray            # (n, n) int64 symmetric, zero diagonal
    offset: int
    logical_vars: int
    W: np.ndarray | None = None   # (n,) knapsack weights, QKP only
    C: int | None = None

    @property
    def spins(self) -> int:
        return len(self.d)

    def energy(self, x) -> int:
        x = np.asarray(x, np.int64)
        return int(self.d @ x + (x @ self.P @ x) // 2 + self.offset)

    def sha256(self) -> str:
        h = hashlib.sha256()
        h.update(f"{self.family}|{self.spins}|{self.offset}|{self.C}".encode())
        for a in (self.d, self.P, self.W):
            if a is not None:
                h.update(np.ascontiguousarray(a, dtype="<i8").tobytes())
        return h.hexdigest()


def _integer(a: np.ndarray, what: str) -> np.ndarray:
    r = np.rint(a)
    if not np.allclose(a, r):
        raise ValueError(f"{what}: non-integer values")
    return r.astype(np.int64)


def from_problem(family: str, problem, logical_vars: int) -> MappedQubo:
    """Map a mc.MaxCut / MaxSat / Colouring through its own to_qubo(); no machine-specific change."""
    Q, c = st.dense_qubo(problem)
    raw = problem.to_qubo()
    c0 = raw[2]
    Qi = _integer(Q, problem.name)
    return MappedQubo(problem.name, family, _integer(c, problem.name), Qi + Qi.T, int(_integer(np.array(c0), "c0")),
                      logical_vars)


def load_maxcut(name: str) -> MappedQubo:
    g = mc.load_gset(name)
    return from_problem("maxcut", g, g.n)


def maxcut_instances(count: int = 10) -> list[MappedQubo]:
    out = [from_problem("maxcut", mc.torus_pm1(L, s), L * L) for L, s in ((6, 1), (8, 1), (8, 2), (10, 1))]
    out += [from_problem("maxcut", mc.random_graph(n, 4 * n, s, pm1=pm), n)
            for n, s, pm in ((32, 1, True), (64, 2, True), (64, 3, False), (100, 4, True), (100, 5, False))]
    out.append(load_maxcut("G1"))
    return out[:count]


def maxsat_instances(count: int = 10) -> list[MappedQubo]:
    specs = [(20, 3), (30, 3), (40, 3), (50, 3), (60, 3), (20, 4), (30, 4), (50, 3), (25, 3), (35, 3)]
    return [from_problem("maxsat", st.random_ksat(nv, round(4.26 * nv), k, seed=100 + i), nv)
            for i, (nv, k) in enumerate(specs[:count])]


def colouring_instances(count: int = 10) -> list[MappedQubo]:
    specs = [(10, 3), (12, 3), (15, 3), (15, 4), (20, 3), (20, 4), (25, 4), (30, 4), (18, 3), (22, 4)]
    return [from_problem("colouring", st.random_colouring(n, 0.3, k, seed=200 + i), n)
            for i, (n, k) in enumerate(specs[:count])]


FAMILIES = {"maxcut": maxcut_instances, "maxsat": maxsat_instances, "colouring": colouring_instances}


def load_qkp(inst) -> MappedQubo:
    """hycim.Inst (integer QKP, maximise profit) -> minimisation form f = -profit with the capacity row attached."""
    n = inst.n
    P = -_integer(inst.off, inst.name)
    return MappedQubo(inst.name, "qkp", -_integer(inst.p, inst.name), P, 0, n, W=np.asarray(inst.w, np.int64),
                      C=int(inst.C))


@dataclass
class Quantised:
    scale: float
    d: np.ndarray
    P: np.ndarray
    loss: dict = field(default_factory=dict)


def quantise(mq: MappedQubo, q: Quantiser) -> Quantised:
    """Common scale s <= 1 so every value fits; round. s = 1 (lossless) when the mapped integers already fit."""
    s = 1.0
    for arr, rng in ((mq.P, q.p_range), (mq.d, q.d_range)):
        if rng is not None:
            lim = min(abs(rng[0]), rng[1])
            top = int(np.abs(arr).max()) if arr.size else 0
            if top > lim:
                s = min(s, lim / top)
    d = np.rint(mq.d * s).astype(np.int64)
    P = np.rint(mq.P * s).astype(np.int64)
    P = np.triu(P, 1)
    P = P + P.T
    rng = np.random.default_rng(LOSS_SEED)
    X = rng.integers(0, 2, size=(LOSS_STATES, mq.spins))
    E = np.array([mq.d @ x + (x @ mq.P @ x) // 2 for x in X], np.float64)
    Eq = np.array([(d @ x + (x @ P @ x) // 2) / s for x in X], np.float64)
    spread = float(E.std()) or 1.0
    changed = float(np.mean((P != mq.P * 1)[np.triu_indices(mq.spins, 1)])) if s != 1.0 else 0.0
    loss = {"scale": s, "frac_couplings_changed": changed,
            "rel_rms_energy_error": float(np.sqrt(np.mean((Eq - E) ** 2)) / spread),
            "lossless": bool(s == 1.0)}
    return Quantised(s, d, P, loss)


def _pad_pow2(d: np.ndarray, P: np.ndarray):
    n = len(d)
    m = max(4, 1 << (n - 1).bit_length())
    dd = np.zeros(m, np.int64)
    PP = np.zeros((m, m), np.int64)
    dd[:n] = d
    PP[:n, :n] = P
    lane = np.zeros(m, bool)
    lane[:n] = True
    return dd, PP, lane


@dataclass
class MachineConfig:
    machine: str
    arms: tuple[str, ...]
    mapped_sha256: str
    spins: int
    quant: Quantised
    instance: object | None   # golden Instance (qubo mode) or hycim.Inst for B2; None if the machine cannot hold it
    fits: bool


def machine_config(machine: str, mq: MappedQubo, *, seed: int = 1, steps: int = 1000, t_start: float = 3.0,
                   t_end: float = 0.1) -> MachineConfig:
    qz = quantise(mq, QUANT[machine])
    inst, fits = None, True
    if machine == "b2":
        import hycim as hc
        qd = mq.W if mq.W is not None else np.ones(mq.spins, np.int64)
        cap = mq.C if mq.C is not None else int(qd.sum())
        inst = hc.Inst(mq.name, -mq.d, -np.triu(mq.P, 1), qd, cap)
        fits = mq.spins <= st.B2_VARS
    else:
        from instances import qubo_instance
        fits = mq.spins <= OURS_MAX_SPINS if machine == "ours" else True
        if fits:
            d, P, lane = _pad_pow2(qz.d, qz.P)
            inst = qubo_instance(d, P, seed=seed, steps=steps, t_start=t_start, t_end=t_end,
                                 deoff=0 if machine == "b1" else 1)
            if mq.spins != len(d):
                inst = type(inst)(**{**inst.__dict__, "lane_en": lane})
    return MachineConfig(machine, ARMS[machine], mq.sha256(), mq.spins, qz, inst, fits)


def machine_configs(mq: MappedQubo, **kw) -> dict[str, MachineConfig]:
    return {m: machine_config(m, mq, **kw) for m in QUANT}


def loss_report(instances: list[MappedQubo]) -> list[dict]:
    rows = []
    for mq in instances:
        for m, cfg in machine_configs(mq).items():
            rows.append({"family": mq.family, "instance": mq.name, "spins": mq.spins, "machine": m,
                         "mapped_sha256": cfg.mapped_sha256[:16], **cfg.quant.loss})
    return rows


def write_report(path: Path = OUT_CSV) -> list[dict]:
    rows = []
    for make in FAMILIES.values():
        rows += loss_report(make())
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    return rows


if __name__ == "__main__":
    for r in write_report():
        print(r["family"], r["instance"], r["spins"], r["machine"], r["scale"], r["rel_rms_energy_error"])
