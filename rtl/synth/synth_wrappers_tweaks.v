// Synthesis-only wrapper (I11/I3/I5 synthesis): accept_unit with the I11 greedy pin tied low, i.e. the v0 machine's lane
// acceptance, so the I11 gating cost is the exact difference to accept_unit with the pin free. Not part of the simulated design.
module syn_accept_g0 #(
    parameter HW = 18,
    parameter TW = 7,
    parameter LW = 12,
    parameter EW = 24
) (
    input  wire signed [HW-1:0] h,
    input  wire signed [HW-1:0] h_acc,
    input  wire                 x,
    input  wire [TW-1:0]        cnt_add,
    input  wire [TW-1:0]        cnt_rem,
    input  wire [15:0]          lam,
    input  wire [2:0]           gsh,
    input  wire [EW-1:0]        eoff,
    input  wire [31:0]          temp,
    input  wire [LW-1:0]        lval,
    output wire signed [HW-1:0] gain,
    output wire                 acc
);
    accept_unit #(.HW(HW), .TW(TW), .LW(LW), .EW(EW)) u (
        .h(h), .h_acc(h_acc), .x(x), .cnt_add(cnt_add), .cnt_rem(cnt_rem), .lam(lam), .gsh(gsh), .eoff(eoff),
        .temp(temp), .lval(lval), .greedy(1'b0), .gain(gain), .acc(acc)
    );
endmodule

// Synthesis-only anchor: one 16 b adder (combinational), the "add (16 b)" of the table row e_add, so that a per-gate switching
// energy can be scaled from e_add by synthesised gate counts. Not part of the simulated design.
module syn_add16 (
    input  wire [15:0] a,
    input  wire [15:0] b,
    output wire [16:0] s
);
    assign s = a + b;
endmodule
