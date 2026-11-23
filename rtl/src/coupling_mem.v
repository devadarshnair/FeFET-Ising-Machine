// Coupling memory of one lane (8-bit signed P) and its bias register (8-bit signed d).
// The coupling memory of the machine is N of these, one per lane: lane j holds row j of P, word k = P_jk.
// On a flip of k every lane reads its own word k at once (registered, one cycle after rd_en), so the lanes see
// column k of P. This is the DA organisation: one broadcast index, one local read and one add per lane, no
// matrix-vector product. The host writes P_jk with wr_p (this lane, word wr_col) and d_j with wr_b.
module coupling_mem #(
    parameter N     = 64,
    parameter LOG2N = $clog2(N),
    parameter JW    = 8,
    parameter BW    = 8,
    parameter DW    = (JW > BW) ? JW : BW
) (
    input  wire             clk,
    input  wire             wr_p,
    input  wire             wr_b,
    input  wire [LOG2N-1:0] wr_col,
    input  wire [DW-1:0]    wr_data,
    input  wire             rd_en,
    input  wire [LOG2N-1:0] rd_col,
    output reg  [JW-1:0]    pk,
    output reg  [BW-1:0]    bias
);
    reg [JW-1:0] mem [0:N-1];

    // Simulation only: a zeroed array lets sparse host scripts (P3.06) skip the zero couplings. Not synthesised.
    // synthesis translate_off
    integer zi;
    initial for (zi = 0; zi < N; zi = zi + 1) mem[zi] = {JW{1'b0}};
    // synthesis translate_on

    always @(posedge clk) begin
        if (wr_p)
            mem[wr_col] <= wr_data[JW-1:0];
        if (wr_b)
            bias <= wr_data[BW-1:0];
        if (rd_en)
            pk <= mem[rd_col];
    end
endmodule
