// Segment adder of the pricer: total count of each row = sum of its NSEG segment counts (combinational).
// Input layout: row r, segment g at r_cnt[(r*NSEG + g)*CW +: CW]. With NSEG = 1 it is a plain copy.
module seg_adder #(
    parameter NROW = 64,
    parameter NSEG = 1,
    parameter CW   = 7,
    parameter TW   = 7
) (
    input  wire [NROW*NSEG*CW-1:0] r_cnt,
    output wire [NROW*TW-1:0]      tot
);
    genvar r;
    generate
        for (r = 0; r < NROW; r = r + 1) begin : row
            integer  g;
            reg [TW-1:0] s;
            always @(*) begin
                s = {TW{1'b0}};
                for (g = 0; g < NSEG; g = g + 1)
                    s = s + r_cnt[(r*NSEG+g)*CW +: CW];
            end
            assign tot[r*TW +: TW] = s;
        end
    endgenerate
endmodule
