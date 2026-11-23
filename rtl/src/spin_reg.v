// Spin register file: one bit x_i per lane. "clr" sets all spins to 0; "flip" toggles spin flip_idx.
module spin_reg #(
    parameter N     = 64,
    parameter LOG2N = $clog2(N)
) (
    input  wire             clk,
    input  wire             clr,
    input  wire             flip,
    input  wire [LOG2N-1:0] flip_idx,
    output reg  [N-1:0]     x
);
    always @(posedge clk) begin
        if (clr)
            x <= {N{1'b0}};
        else if (flip)
            x[flip_idx] <= ~x[flip_idx];
    end
endmodule
