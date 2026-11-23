// Acceptance unit, one per lane, combinational (SPEC section 5.2):
//   gain  = x ? -h : h
//   geff  = (gain << gsh) - lam*cnt_add + lam*cnt_rem          (energy LSB)
//   theta = (temp * lval) >> 24                                (temp UQ16.16, lval UQ4.8)
//   acc   = (geff + eoff + theta >= 0)        (greedy, I11: theta = eoff = 0)
// All terms are exact; SW is wide enough that the sum cannot overflow.
// verilator lint_off WIDTHEXPAND   // terms are sign/zero-extended into the SW-bit sum; SW is wide enough that nothing overflows (SPEC 5.2, tb_accept)
// verilator lint_off UNUSEDSIGNAL   // only the top bits of the temp*lval product are the threshold; low 24 bits dropped by the UQ16.16 x UQ4.8 >> 24
module accept_unit #(
    parameter HW = 18,
    parameter TW = 7,
    parameter LW = 12,
    parameter EW = 24
) (
    input  wire signed [HW-1:0] h,
    input  wire signed [HW-1:0] h_acc,      // field used for the acceptance (= h, or the CiM field)
    input  wire                 x,
    input  wire [TW-1:0]        cnt_add,
    input  wire [TW-1:0]        cnt_rem,
    input  wire [15:0]          lam,
    input  wire [2:0]           gsh,
    input  wire [EW-1:0]        eoff,
    input  wire [31:0]          temp,
    input  wire [LW-1:0]        lval,
    input  wire                 greedy,     // I11: theta = 0 and E_off = 0 (acc = geff >= 0)
    output wire signed [HW-1:0] gain,
    output wire                 acc
);
    localparam PW  = 16 + TW;                 // penalty product bits
    localparam THW = 32 + LW - 24;            // threshold bits
    localparam M1  = (PW > EW) ? PW : EW;
    localparam M2  = (M1 > THW) ? M1 : THW;
    localparam M3  = (M2 > HW + 4) ? M2 : HW + 4;
    localparam SW  = M3 + 4;                  // five terms: three extra bits of growth plus sign

    assign gain = x ? -h : h;

    wire signed [HW-1:0]  gain_a = x ? -h_acc : h_acc;
    wire signed [SW-1:0]  g_ext = gain_a;
    wire signed [SW-1:0]  qg    = g_ext <<< gsh;
    wire [PW-1:0]         pa    = lam * cnt_add;
    wire [PW-1:0]         pr    = lam * cnt_rem;
    wire [32+LW-1:0]      tl    = temp * lval;
    wire [THW-1:0]        theta = tl[32+LW-1:24];

    wire signed [SW-1:0] sum = qg - $signed({1'b0, pa}) + $signed({1'b0, pr})
                             + $signed({1'b0, greedy ? {EW{1'b0}} : eoff}) + $signed({1'b0, greedy ? {THW{1'b0}} : theta});

    assign acc = ~sum[SW-1];
endmodule
// verilator lint_on WIDTHEXPAND
// verilator lint_on UNUSEDSIGNAL
