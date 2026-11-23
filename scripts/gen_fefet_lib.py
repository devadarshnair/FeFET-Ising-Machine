"""Generate device/ngspice/fefet_preisach.lib from device/params/set{A,B,C}.json.

The ngspice-native FeFET model needs one state node per domain, so the N domains are written
out by hand. This script does that, so that the .lib always matches the parameter files.
The equations are the ones in device/veriloga/fefet_preisach.va (see
docs/device/MODEL_EQUIVALENCE.md).

Usage (from the repo root, through the memory guard):
    scripts/run_guarded.sh <python> scripts/gen_fefet_lib.py           # write the .lib
    scripts/run_guarded.sh <python> scripts/gen_fefet_lib.py --check   # exit 1 if out of date
"""
import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "device" / "py"))
import fefet_ref  # noqa: E402

OUT = REPO / "device" / "ngspice" / "fefet_preisach.lib"
EPS0 = fefet_ref.EPS0
DIFF_LEN = 90e-9  # source/drain diffusion length used for as/ad/ps/pd of the FeFET channel


def num(v):
    return f"{v:.6g}"


def wrap(head, items, width=100):
    """Write 'head item item ...' with ngspice '+' continuation lines."""
    lines, cur = [], head
    for it in items:
        if len(cur) + 1 + len(it) > width:
            lines.append(cur)
            cur = "+ " + it
        else:
            cur = cur + " " + it
    lines.append(cur)
    return "\n".join(lines)


def core(n, beta_one):
    """FE core between nodes t (top, gate side) and b (bottom, internal node m)."""
    name = f"fe_core{n}" + ("_b1" if beta_one else "")
    params = ["area=1e-12", "tfe=10e-9", "psat=0.25", "epsr=30", "tauinf=1e-6", "alpha=2",
              "vimp=0", "gleak=0"]
    if not beta_one:
        params += ["beta=1", "h0=1e-6"]
    params += [f"ea{i}=2e8" for i in range(1, n + 1)]
    params += [f"x0_{i}=0" for i in range(1, n + 1)]
    out = [f"* {name}: {n}-domain kinetic Preisach ferroelectric between t and b, "
           + ("beta = 1 form (R3a)." if beta_one else "general-beta form (R3b).")]
    out.append(wrap(f".subckt {name} t b params:", params))
    out.append("* (R2) NLS rate 1/tau = exp(-min((va/|v+vimp|)^alpha, 200))/tauinf, |v+vimp| floored at 1 mV")
    out.append(".func nlsr(v, va) {exp(-min(pwr(va/max(abs(v+vimp), 1e-3), alpha), 200))/tauinf}")
    if beta_one:
        out.append("* (R3a) dx/dt = r*(sgn(E) - x)")
        out.append(".func dxdt1(v, x, va) {nlsr(v, va)*(sgn(v+vimp) - x)}")
    else:
        out.append("* (R3b) dx/dt = sgn(E)*beta*r*(1 - sgn(E)*x)*(-ln((1 - sgn(E)*x)/2) + h0)^((beta-1)/beta)")
        out.append(".func dxdtg(v, x, va) {sgn(v+vimp)*beta*nlsr(v, va)*(1 - sgn(v+vimp)*x)"
                   "*pwr(max(-ln(max(0.5*(1 - sgn(v+vimp)*x), 1e-300)), 0) + h0, (beta-1)/beta)}")
    out.append("* domain states: x_i is the voltage on a 1 F capacitor, dx_i/dt = dxdt(V_FE, x_i, E_a,i * t_FE)")
    for i in range(1, n + 1):
        out.append(f"Cx{i} x{i} 0 1 ic={{x0_{i}}}")
        out.append(f"Bx{i} 0 x{i} I = " + ("dxdt1" if beta_one else "dxdtg") + f"(v(t,b), v(x{i}), {{ea{i}*tfe}})")
    terms = "+".join(f"v(x{i})" for i in range(1, n + 1))
    out.append("* (R4) mean domain state; (R5) polarization current area*psat*d(mean x)/dt,")
    out.append("* sensed as the current into a capacitor of value area*psat driven by the mean")
    out.append(f"Bsum xs 0 V = ({terms})/{n}")
    out.append("Vps xs xsc 0")
    x0mean = "+".join(f"x0_{i}" for i in range(1, n + 1))
    out.append("* its start voltage = mean start state, so no charge is pushed into b at t = 0")
    out.append(f"Cps xsc 0 {{area*psat}} ic={{({x0mean})/{n}}}")
    out.append("Fpol t b Vps 1")
    out.append("* (R5) linear dielectric part: area*eps0*epsr/tfe")
    out.append(f"Cfe t b {{area*{EPS0:.10g}*epsr/tfe}}")
    out.append("* optional FE leakage conductance (default 0 = off)")
    out.append("Bleak t b I = {gleak}*v(t,b)")
    out.append(f".ends {name}")
    return "\n".join(out)


def set_values(p, n=None):
    n = p["N"] if n is None else n
    ea = fefet_ref.activation_fields(p, n)
    vals = {"tfe": p["t_fe_m"], "psat": p["P_S_C_per_m2"], "epsr": p["eps_r"],
            "tauinf": p["tau_inf_s"], "alpha": p["alpha"], "vimp": p["V_imp_V"]}
    if p["beta"] != 1.0:
        vals.update({"beta": p["beta"], "h0": p["h0"]})
    return vals, ea


def fecap_wrapper(p, n, name):
    vals, ea = set_values(p, n)
    core_name = f"fe_core{n}" + ("_b1" if p["beta"] == 1.0 else "")
    params = ["area=1e-12"] + [f"x0_{i}=-1" for i in range(1, n + 1)]
    out = [f"* {name}: MFM capacitor, parameter set {p['name']}, {n} domain(s). Default start state x = -1."]
    out.append(wrap(f".subckt {name} t b params:", params))
    inst = [f"area={{area}}"] + [f"{k}={num(v)}" for k, v in vals.items()]
    inst += [f"ea{i}={num(e)}" for i, e in enumerate(ea, 1)]
    inst += [f"x0_{i}={{x0_{i}}}" for i in range(1, n + 1)]
    out.append(wrap(f"Xfe t b {core_name}", inst))
    out.append(f".ends {name}")
    return "\n".join(out)


def fefet_wrapper(p, name):
    n = p["N"]
    vals, ea = set_values(p, n)
    f = p["fefet"]
    core_name = f"fe_core{n}" + ("_b1" if p["beta"] == 1.0 else "")
    params = [f"w={num(f['W_m'])}", f"l={num(f['L_m'])}", f"ra={num(f['r_A'])}", "dvt=0", "dvg=0", "rm=1e25"]
    params += [f"ea{i}={num(e)}" for i, e in enumerate(ea, 1)]
    params += [f"x0_{i}=0" for i in range(1, n + 1)]
    out = [f"* {name}: FeFET, parameter set {p['name']}: FE ({n} domains) from gate g to internal node m,"]
    out.append(f"* MOSFET {f['card']['name']} (d, m, s, b). dvt = BSIM4 delvto of the channel (V).")
    out.append("* dvg = gate-referred threshold shift (V): a source in series with the gate, so V_th moves by")
    out.append("* exactly dvg in every state (used for Monte Carlo of V_th variation).")
    out.append("* ea1..: per-domain activation fields (V/m), defaults = set quantiles. x0_1..: start states.")
    out.append(wrap(f".subckt {name} g d s b params:", params))
    inst = ["area={w*l*ra}"] + [f"{k}={num(v)}" for k, v in vals.items()]
    inst += [f"ea{i}={{ea{i}}}" for i in range(1, n + 1)]
    inst += [f"x0_{i}={{x0_{i}}}" for i in range(1, n + 1)]
    out.append("Vdvg g gi {dvg}")
    out.append(wrap(f"Xfe gi m {core_name}", inst))
    out.append(f"M1 d m s b {f['card']['name']} w={{w}} l={{l}} delvto={{dvt}} as={{w*{num(DIFF_LEN)}}} "
               f"ad={{w*{num(DIFF_LEN)}}} ps={{2*w+{num(2 * DIFF_LEN)}}} pd={{2*w+{num(2 * DIFF_LEN)}}}")
    out.append("* (R7) very large resistor m->s: numerical safety only, time constant >> any run")
    out.append("Rm m s {rm}")
    out.append(f".ends {name}")
    return "\n".join(out)


def fefet_frozen(p, name):
    """Same FeFET with the domain states frozen: only the linear FE capacitor and the MOSFET.
    Valid only where no domain can switch (ns-scale searches at <= 1.1 V); the polarization
    charge is then constant and lives in the start voltage of node m (.ic from a saved state)."""
    f = p["fefet"]
    out = [f"* {name}: FeFET of set {p['name']} with FROZEN domain states, for nanosecond searches only.",
           "* Start it from a saved state: .ic v(<inst>.m)=V_m of the full model. Checked against the",
           "* full model in test 3b (t3b.frozen_equiv)."]
    out.append(wrap(f".subckt {name} g d s b params:",
                    [f"w={num(f['W_m'])}", f"l={num(f['L_m'])}", f"ra={num(f['r_A'])}", "dvt=0", "dvg=0", "rm=1e25"]))
    out.append("Vdvg g gi {dvg}")
    out.append(f"Cfe gi m {{w*l*ra*{EPS0:.10g}*{num(p['eps_r'])}/{num(p['t_fe_m'])}}}")
    out.append(f"M1 d m s b {f['card']['name']} w={{w}} l={{l}} delvto={{dvt}} as={{w*{num(DIFF_LEN)}}} "
               f"ad={{w*{num(DIFF_LEN)}}} ps={{2*w+{num(2 * DIFF_LEN)}}} pd={{2*w+{num(2 * DIFF_LEN)}}}")
    out.append("Rm m s {rm}")
    out.append(f".ends {name}")
    return "\n".join(out)


def card(p):
    c = p["fefet"]["card"]
    keys = ["toxe", "toxp", "toxm", "vth0", "xj", "u0", "vsat", "rdsw", "cit"]
    body = " ".join(f"{k}={num(c[k])}" for k in keys)
    return "\n".join([
        f"* {c['name']}: channel of the set-{p['name']} FeFET. UNCALIBRATED STAND-IN BSIM4 card, written by",
        "* hand like models/mosfet/standin45_bsim4.lib, with tox = the SiO2 interlayer and vth0 fitted",
        "* so that the FeFET thresholds land on the set's targets (docs/device/CALIBRATION_v0.md).",
        wrap(f".model {c['name']} nmos level=54 version=4.8", body.split() + [
            "epsrox=3.9", "cgso=1.0e-10", "cgdo=1.0e-10", "cjs=1.0e-3", "cjd=1.0e-3",
            "cjsws=1.0e-10", "cjswd=1.0e-10"]),
    ])


def header(sets):
    out = ["* fefet_preisach.lib -- GENERATED by scripts/gen_fefet_lib.py from device/params/*.json.",
           "* Do not edit by hand: change the JSON (or the generator) and regenerate.",
           "*",
           "* this project v0 FeFET compact model, ngspice-native form (B-sources and 1 F state capacitors).",
           "* Canonical source of the equations: device/veriloga/fefet_preisach.va.",
           "* Equation-by-equation correspondence: docs/device/MODEL_EQUIVALENCE.md.",
           "*",
           "* Use only with transient analysis and 'uic' (the internal node m has no DC path).",
           "* Run ngspice with -n so that a user ~/.spiceinit (e.g. HSPICE compatibility) is not loaded.",
           "*",
           "* Parameter sets (activation fields at equal-probability mid-quantiles, MV/cm):"]
    for p in sets:
        ea = fefet_ref.activation_fields(p) / 1e8
        out.append(f"*  set {p['name']}: t_FE {p['t_fe_m']*1e9:.3g} nm, P_S {p['P_S_C_per_m2']*100:.4g} uC/cm^2, "
                   f"eps_r {p['eps_r']:.4g}, tau_inf {p['tau_inf_s']:.4g} s, alpha {p['alpha']:.4g}, "
                   f"beta {p['beta']:.4g}, V_imp {p['V_imp_V']:.4g} V, N {p['N']}")
        out.append("*    E_a: " + " ".join(f"{e:.3f}" for e in ea))
    return "\n".join(out)


def build():
    sa, sb, sc = (fefet_ref.load_set(k) for k in "ABC")
    parts = [header([sa, sb, sc]), ""]
    for n in sorted({1, sa["N"], sb["N"], sc["N"]}):
        parts += [core(n, beta_one=False), "", core(n, beta_one=True), ""]
    parts += [fecap_wrapper(sa, 1, "fecap_a1"), "", fecap_wrapper(sa, sa["N"], f"fecap_a{sa['N']}"), ""]
    parts += [fecap_wrapper(sb, sb["N"], f"fecap_b{sb['N']}"), ""]
    parts += [fecap_wrapper(sc, sc["N"], f"fecap_c{sc['N']}"), ""]
    parts += [card(sb), "", fefet_wrapper(sb, f"fefet_b{sb['N']}"), ""]
    parts += [card(sc), "", fefet_wrapper(sc, f"fefet_c{sc['N']}"), ""]
    parts += [fefet_frozen(sc, f"fefet_c{sc['N']}_frozen"), ""]
    return "\n".join(parts) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="exit 1 if the committed .lib is out of date")
    args = ap.parse_args()
    text = build()
    if args.check:
        same = OUT.exists() and OUT.read_text() == text
        print("gen_fefet_lib: up to date" if same else "gen_fefet_lib: OUT OF DATE")
        sys.exit(0 if same else 1)
    OUT.write_text(text)
    print(f"gen_fefet_lib: wrote {OUT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
