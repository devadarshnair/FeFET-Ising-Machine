# MOSFET card choice (written 15 Nov 2026, before the sanity run)

- Primary: FreePDK45 NCSU basekit nominal BSIM4 cards NMOS_VTG / PMOS_VTG (Apache-2.0), exposed as `nmos45`/`pmos45` by `pdk45.lib`.
  VTG = regular-threshold device (vth0 +0.41 V / -0.38 V, toxe 1.14/1.26 nm). VTL (low Vt) and VTH (high Vt) cards stay in `freepdk45/` for later use.
- Sensitivity (H3): PTM 45 nm HP (`ptm45.lib`, vth0 +0.469 V NMOS). LP card is kept in `ptm45/` but not wrapped. FreePDK45 cards are
  themselves "customised PTM 45", so the two are related, not independent; H3 reads it as a card-parameter sensitivity, not an independent PDK.
- Stand-in `standin45_bsim4.lib` stays untouched as the v0 reference.
- Sanity check (fixed before running): `tb_pdk45.cir` (same deck as `tb_standin45.cir`, include switched; run from this folder) must run without
  error, print Id at Vgs = 1 V (`ion_n`), and give nmos subthreshold slope `ss_n_mv_per_dec` between 60 and 120 mV/dec. Same check for `tb_ptm45.cir`.
- Both card sets are data-only files (verified: only `.model`, continuation and comment lines); read in full before `.include`.

Deck note (15 Nov 2026, same attempt): in the copied decks the SS points were first taken at |Vds| = 1 V as in the stand-in deck, but the
real cards leak 20-55 nA/um at Vgs = 0 and Vds = 1 V, above the 10 nA first point, so the measure was out of range (error, no number).
The SS points were moved to the |Vds| = 50 mV sweep (currents 10 nA and 100 nA). The 60-120 mV/dec window is unchanged.

Result (15 Nov 2026): pdk45 (FreePDK45 VTG): Id(Vgs = 1 V, Vds = 1 V) = 1.15 mA/um, Vth(sat) 0.14 V, Ioff 55 nA/um, SS 85.1 mV/dec,
pmos Ion 0.80 mA/um -> PASS. ptm45 (HP): Ion 1.33 mA/um, Ioff 21 nA/um, SS 87.9 mV/dec -> PASS. Note the high Ioff (DIBL, 45 nm HP-class cards); the
low-leakage choice, if later needed, is the FreePDK45 VTH card, not a change of tolerance.
