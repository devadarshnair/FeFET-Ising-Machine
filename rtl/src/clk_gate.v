// Clock gate (ICG model). gclk = clk & en_q, where en_q is the enable sampled while the clock is low, so gclk never glitches: valid
// because `en` only changes shortly after a rising edge (it is decoded from FSM state registers). Equivalent to the latch-based
// integrated clock gate of a library (Nangate45 CLKGATETST_X1, used for the timing study v1 power measurement in rtl/pnr/tt_wrappers.v);
// the negedge-register form is used in RTL because every simulator (Icarus, Verilator) schedules it without races.
// Flops on gclk see the same data as flops on clk: gclk rises in the active region right after clk, before any non-blocking update.
module clk_gate (
    input  wire clk,
    input  wire en,
    output wire gclk
);
    reg en_q;
    always @(negedge clk) en_q <= en;
    assign gclk = clk & en_q;
endmodule
