// Dynamic offset E_off (escape logic, SPEC section 5.4). At each step update: reset to 0 when a flip is applied,
// else grow by deoff, saturating at 2^EW - 1.
// verilator lint_off WIDTHEXPAND   // 16 b step added to the 24 b offset; the carry bit is the saturation flag
module offset_unit #(
    parameter EW = 24
) (
    input  wire          clk,
    input  wire          clr,
    input  wire          upd,
    input  wire          accepted,
    input  wire [15:0]   deoff,
    output reg  [EW-1:0] eoff
);
    wire [EW:0] grown = eoff + deoff;

    always @(posedge clk) begin
        if (clr)
            eoff <= {EW{1'b0}};
        else if (upd)
            eoff <= accepted ? {EW{1'b0}} : (grown[EW] ? {EW{1'b1}} : grown[EW-1:0]);
    end
endmodule
// verilator lint_on WIDTHEXPAND
