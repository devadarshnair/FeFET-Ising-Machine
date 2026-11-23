// Query encoder of the TCAM pricer (SPEC section 5.1 step 2). From each slack s_j it builds the thermometer masks:
//   ADD mask bit (j,k) = (Q*s_j < k*wmax)      i.e. level k is above floor(Q*max(s_j,0)/wmax)
//   REM mask bit (j,k) = (k*wmax <= -Q*s_j)    i.e. level k is at or below floor(Q*max(-s_j,0)/wmax)
// for k = 1..Q (Q = NLEV, a power of two), at column j*Q + (k-1). Unused columns get 0. Outputs are registered
// when ld = 1. No divider: Q*s is a shift and k*wmax is a constant multiple.
// verilator lint_off WIDTHEXPAND   // signed slack widened into the XW-bit scaled comparison
module query_enc #(
    parameter NCON = 8,
    parameter NLEV = 8,
    parameter SEGW = 64,
    parameter NSEG = 1,
    parameter LDW  = 16
) (
    input  wire                    clk,
    input  wire                    ld,
    input  wire [NCON*(LDW+1)-1:0] slack,
    input  wire [5:0]              wmax,
    output reg  [NSEG*SEGW-1:0]    add_mask,
    output reg  [NSEG*SEGW-1:0]    rem_mask
);
    localparam QSH = $clog2(NLEV);
    localparam XW  = LDW + 1 + QSH + 1;      // signed width for Q*s, -Q*s and k*wmax
    localparam NC  = NCON * NLEV;            // used columns

    wire [NSEG*SEGW-1:0] add_c;
    wire [NSEG*SEGW-1:0] rem_c;

    genvar j, k;
    generate
        for (j = 0; j < NCON; j = j + 1) begin : con
            wire signed [LDW:0]  s  = slack[j*(LDW+1) +: (LDW+1)];
            wire signed [XW-1:0] qs = s <<< QSH;
            wire signed [XW-1:0] nq = -qs;
            for (k = 1; k <= NLEV; k = k + 1) begin : lev
                wire signed [XW-1:0] kw = $signed({{(XW-6){1'b0}}, wmax}) * k;
                assign add_c[j*NLEV + k - 1] = (qs < kw);
                assign rem_c[j*NLEV + k - 1] = (kw <= nq);
            end
        end
        if (NC < NSEG*SEGW) begin : pad
            assign add_c[NSEG*SEGW-1:NC] = {(NSEG*SEGW-NC){1'b0}};
            assign rem_c[NSEG*SEGW-1:NC] = {(NSEG*SEGW-NC){1'b0}};
        end
    endgenerate

    always @(posedge clk) begin
        if (ld) begin
            add_mask <= add_c;
            rem_mask <= rem_c;
        end
    end
endmodule
// verilator lint_on WIDTHEXPAND
