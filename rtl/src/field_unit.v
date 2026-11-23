// Local field of one lane with incremental update (HW-bit signed). The local-field array is N of these.
// init: h = d (all spins 0). upd: h = h + P_ik if dir = 1 (spin k goes 0 -> 1), h - P_ik if dir = 0.
// ovf is a sticky flag: the field left the HW-bit range (it never should at the widths of SPEC section 3).
// verilator lint_off WIDTHEXPAND   // signed p8/b8 are sign-extended into the wider field register on purpose (SPEC 3 widths)
module field_unit #(
    parameter JW = 8,
    parameter BW = 8,
    parameter HW = 18
) (
    input  wire          clk,
    input  wire          init,
    input  wire [BW-1:0] bias,
    input  wire          upd,
    input  wire          dir,
    input  wire [JW-1:0] pk,
    output wire [HW-1:0] h,
    output reg           ovf
);
    reg signed [HW-1:0] hr;
    wire signed [JW-1:0] p8  = pk;
    wire signed [BW-1:0] b8  = bias;
    wire signed [HW:0]   sum = dir ? (hr + p8) : (hr - p8);   // one extra bit to see overflow

    always @(posedge clk) begin
        if (init) begin
            hr  <= b8;
            ovf <= 1'b0;
        end else if (upd) begin
            hr <= sum[HW-1:0];
            if (sum[HW] != sum[HW-1])
                ovf <= 1'b1;
        end
    end

    assign h = hr;
endmodule
// verilator lint_on WIDTHEXPAND
