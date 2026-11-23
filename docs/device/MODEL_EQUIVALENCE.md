# FeFET model v0: the same equations in three places

The canonical source is `device/veriloga/fefet_preisach.va` (module `fe_preisach16`). It is not
compiled yet (OpenVAF is not installed). What runs now is the ngspice-native subcircuit in
`device/ngspice/fefet_preisach.lib`, written by `scripts/gen_fefet_lib.py` from
`device/params/set{A,B,C}.json`. `device/py/fefet_ref.py` holds the same equations for offline
references and fitting. Recipe numbers (R1-R7) refer to `docs/lit/device_models.md` §1.2.

Symbols: V_FE = V(g) − V(m) (gate side minus internal node); v = V_FE + V_imp; x_i = state of domain
i (−1 … +1); s = sign(v); va_i = E_a,i · t_FE; N = 16.

| Eq. | Meaning | Verilog-A (`fefet_preisach.va`) | ngspice-native (`fefet_preisach.lib`) | Python (`fefet_ref.py`) |
|---|---|---|---|---|
| R1 | FE voltage and imprint | `vfe = V(t,b); v = vfe + vimp` | `v(t,b)` passed to `.func`, `+vimp` inside it | `v_fe + p["V_imp_V"]` |
| R2 | NLS rate, capped | `r = exp(-min(pow(va/max(abs(v),1e-3), alp), 200))/tau` | `.func nlsr(v,va) {exp(-min(pwr(va/max(abs(v+vimp),1e-3),alpha),200))/tauinf}` | `rate()` |
| R3a | β = 1 state ODE | (general form with bet = 1) | `.func dxdt1(v,x,va) {nlsr(v,va)*(sgn(v+vimp)-x)}` in `fe_core16_b1` | `dxdt()`, β = 1 branch |
| R3b | β ≠ 1 state ODE | `dxdt = sg*bet*r*om*pow(hist,(bet-1)/bet)`, `om = 1 - sg*x`, `hist = max(-ln(max(om/2,1e-300)),0) + h0` | `.func dxdtg(...)`, same expression, in `fe_core16` | `dxdt()`, general branch |
| state | how the state is stored | node `xi` holds the **deviation** from the start state: `xx_i = x0_i + V(xi)`; `I(xi) <+ ddt(V(xi)) - dxdt(...) + gx*V(xi)` | node `xi` holds x_i itself: `Cxi xi 0 1 ic={x0_i}` and `Bxi 0 xi I = dxdt(...)` | vector `x` integrated with `solve_ivp` (Radau) |
| R4 | polarization | `psum = (xx1+…+xx16)/16`, P = psat·psum | `Bsum xs 0 V = (v(x1)+…+v(x16))/16` | `P_S * mean(x)` |
| R5 | FE current | `I(t,b) <+ ddt(area*(psat*psum + eps0*epsr*v/tfe))` | polarization part: `Cps xsc 0 {area*psat}` driven by `xs` through `Vps`, mirrored by `Fpol t b Vps 1`; dielectric part: `Cfe t b {area*eps0*epsr/tfe}` | `MosTable` + charge balance on node m (`FeFETReduced.vm`) |
| R5 | FE leakage (off by default) | `I(t,b) <+ gleak*vfe` | `Bleak t b I = {gleak}*v(t,b)` | not modelled |
| R6 | MOSFET | separate built-in BSIM4 instance in the netlist (d, m, s, b) | `M1 d m s b nfefet_<set>` inside `fefet_<set>16` | tabulated gate charge and drain current of the same card (`device/tb/mos_table.cir`) |
| R7 | node m DC path | (netlist) `Rm m s 1e25` | `Rm m s {rm}`, rm = 1e25 Ω | none needed |
| var. | V_th shift for Monte Carlo | (netlist) source in series with the gate | `Vdvg g gi {dvg}` in `fefet_<set>16` | not modelled |

Why the forms differ and why they are still the same equations:

- **State storage.** Verilog-A has no per-node initial condition, so the `.va` stores the deviation
  from the start state; with `uic` (or a DC start, where the tiny `gx` term makes the problem
  well posed) the node starts at 0, i.e. x_i = x0_i. The `.lib` stores x_i directly with a capacitor
  `ic=`. A change of variable, nothing more.
- **Polarization current.** `ddt(area·psat·psum)` in Verilog-A is the current into a capacitor of
  value area·psat driven by psum; the `.lib` builds exactly that (Cps, sensed by Vps) and copies the
  current from t to b with a unit-gain F source. Both are integrated by the simulator's own
  integration formula, so the charge pushed into node m stays consistent with the domain states
  (test t1a.charge: 0.12 %). The sensing capacitor starts at the mean start state (`ic=`), so no
  charge is pushed into m at t = 0 (an early version had this kick; it was found by a restart probe).
- **Dielectric term.** The recipe writes ε0·εr·E with E including V_imp. Since V_imp is constant its
  time derivative is zero, so the `.lib` uses a plain capacitor; the `.va` keeps v in the ddt.
- **sign(v) at v = 0.** Both forms jump at v = 0, but the rate there is exp(−200)/τ∞ (the
  exponent is capped), about 1e-87/τ∞, so the jump has no effect on the solution.
- **Python.** The offline model eliminates node m by charge conservation instead of solving it as a
  node: Q_mos(V_m) − C_lin(V_g − V_m) − A·P = constant. Its MOS table must come from the integrated
  gate terminal current, because BSIM4's reported `qg`/`cgg` leave out the fringing and overlap
  charge (about 0.09 fF for the set-C device; found when ngspice and Python disagreed by 50 mV).
  With that table and the same read ramp, the two agree within a few mV (test t1f.ref_agree).
