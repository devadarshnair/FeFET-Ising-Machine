"""Write the vector files for rtl/tb/tb_cim_field.v from the golden CimField (P3.03).

Usage: gen_cim_vectors.py <out_dir>   writes cim_vec0.txt (no noise) and cim_vec1.txt (xorshift32 noise).
File format (whitespace tokens, all decimal except x): N seed32 sg, N*N P (row-major), N d, V, then V records
`<x hex> <adc_bits> <N expected h values>`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from cim_field import CimCfg, CimField  # noqa: E402

N = 16
VECTORS = 3000


def write_file(path: Path, noise: bool, seed_rng: int) -> int:
    rng = np.random.default_rng(seed_rng)
    P = rng.integers(-127, 128, size=(N, N)) * (rng.random((N, N)) < 0.6)
    P = np.triu(P, 1)
    P = (P + P.T).astype(np.int64)
    d = rng.integers(-128, 128, size=N).astype(np.int64)
    seed32, sg = (0xC0FFEE11, 1800) if noise else (0, 0)
    cf = CimField(CimCfg(adc_bits=16, w_bits=8, lfsr=noise, sg=sg, seed=seed32), P, d)
    lines = [f"{N} {seed32} {sg}", " ".join(str(v) for v in P.ravel()), " ".join(str(v) for v in d), str(VECTORS)]
    clipped = 0
    for _ in range(VECTORS):
        x = rng.integers(0, 2, size=N) * (rng.random(N) < rng.choice([0.2, 0.5, 0.9]))
        bits = int(rng.integers(2, 17))
        cf.set_bits(bits)
        h = cf.field(x)
        clipped += int(cf.lsb > 1)
        xv = sum(int(b) << i for i, b in enumerate(x))
        lines.append(f"{xv:x} {bits} " + " ".join(str(int(v)) for v in h))
    path.write_text("\n".join(lines) + "\n")
    return clipped


def generate(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for k, noise in enumerate((False, True)):
        q = write_file(out / f"cim_vec{k}.txt", noise, 1000 + k)
        print(f"cim_vec{k}: {VECTORS} vectors, noise={noise}, {q} with LSB > 1")


if __name__ == "__main__":
    generate(Path(sys.argv[1]))
