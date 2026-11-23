# FreePDK45 NCSU basekit, HSPICE nominal BSIM4 (level 54) model cards
- Origin: NCSU FreePDK45 (https://eda.ncsu.edu/freepdk/freepdk45/). Licence: Apache-2.0 (file LICENSE; the kit ships APACHE-LICENSE-2.0.txt).
- Fetched 15 Nov 2026 (IST) from the GitHub mirror https://github.com/baichen318/FreePDK45 at commit a75cb116a3efd1d3ae05b695285452e6ffbc7ca5,
  path FreePDK45/ncsu_basekit/models/hspice/ (tran_models/models_nom/*.inc, hspice_nom.include, ptm/README) and FreePDK45/APACHE-LICENSE-2.0.txt.
  The official NCSU download host was not used; the mirror files are unmodified copies of the kit files (not checksum-compared against NCSU).
- Cards are the nominal corner only. Header of each: "Customized PTM 45" (FreePDK45 cards derive from PTM 45 nm). Read in full; data only
  (only .model, continuation and comment lines). genptm.pl was NOT downloaded or run.
- Files used by the wrapper: NMOS_VTG.inc / PMOS_VTG.inc (regular threshold). Others kept for reference (VTL, VTH, THKOX).
- SHA-256:
```
302d7e4d88a72840ebd88077a12186a67028478c4d842d8294f1d67860c4d75f  NMOS_THKOX.inc
3cb730470427d99b6d22ab4d029493fa949daa1040d2ed51179118263682a14c  NMOS_VTG.inc
f869d191bd3d173491dec6d8b5d31c0a35a60b6e75a86e9644515a8efa92566f  NMOS_VTH.inc
e5a86b413e3c58c0d4f1fc6e3e0388e49d0ad040ba72f4593d2364a177786ad6  NMOS_VTL.inc
fdaee8972a4fdce1d3e29d397adea973d3a840df099cc360d7115bbe5d532b22  PMOS_THKOX.inc
a7d95a2631897134d2f52a9fa8469aef4e7c6dd2a2b5a499fc08645da3465d4a  PMOS_VTG.inc
3cf2067bdbe27fb574bba97292e254c7769e9d706e7bfd9692e951f505b2c19a  PMOS_VTH.inc
97fc614d8e96884ed31ea9c25509919edecd80fec06270ec17b661e6dfdbb8eb  PMOS_VTL.inc
ef87bf2f5c1ed39ab12c2be6df9a1c8f5cd9546413cab04614b8da28bd4fe406  hspice_nom.include
59899c6091b540582ed617e8eeaac4919dc985ccfc35459ee9752b699be5205b  LICENSE
1da43901da0a533a8909d8fd5a6a708cc996a295a5c5645695feaf9646491b29  GENPTM_README.txt
```
