// Acceptance lookup table of one lane: L[a] ~ -ln u in UQ4.8 (nats), 2^LAB entries of LW bits.
// Every lane has its own copy (as an FPGA would, in distributed ROM); the host writes all copies at once.
// This is the DA patent's "RAM conversion table". Contents: SPEC section 5.2 (the golden model generates them).
module accept_lut #(
    parameter LAB = 10,
    parameter LW  = 12
) (
    input  wire           clk,
    input  wire           wr,
    input  wire [LAB-1:0] wr_addr,
    input  wire [LW-1:0]  wr_data,
    input  wire [LAB-1:0] rd_addr,
    output wire [LW-1:0]  rd_data
);
    reg [LW-1:0] lut [0:(1<<LAB)-1];

    always @(posedge clk) begin
        if (wr)
            lut[wr_addr] <= wr_data;
    end

    assign rd_data = lut[rd_addr];
endmodule
