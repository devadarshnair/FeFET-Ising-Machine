// Uniform selection of one accepted lane by a count-tree walk (SPEC section 5.3). Combinational.
//   count = popcount(acc);  r = (r16 * count) >> 16;  idx = index of the r-th set bit of acc (r = 0 is the lowest)
// Tree in heap order: node 1 is the root, node n has children 2n and 2n+1, leaf N+i is acc[i]. Each node holds the
// popcount of its subtree. The walk goes left when r < left count, else it subtracts the left count and goes
// right; after log2(N) levels it is at leaf N+idx. N must be a power of two.
// Written as one procedural block (the loops unroll to the adder tree and log2(N) compare/subtract stages).
// verilator lint_off UNUSEDSIGNAL   // only the high 16 bits of the r16 * count product select the accepted lane (fixed-point multiply)
module select_tree #(
    parameter N     = 64,
    parameter LOG2N = $clog2(N)
) (
    input  wire [N-1:0]     acc,
    input  wire [15:0]      r16,
    output wire             valid,
    output reg  [LOG2N-1:0] idx,
    output reg  [LOG2N:0]   count
);
    localparam CWD = LOG2N + 1;

    reg [CWD-1:0]     node [1:2*N-1];
    reg [16+CWD-1:0]  prod;
    reg [CWD-1:0]     rr;
    reg [CWD:0]       nd;
    integer           i, lvl;

    always @(acc or r16) begin
        for (i = 0; i < N; i = i + 1)
            node[N+i] = {{(CWD-1){1'b0}}, acc[i]};
        for (i = N - 1; i >= 1; i = i - 1)
            node[i] = node[2*i] + node[2*i+1];
        count = node[1];
        prod  = r16 * node[1];
        rr    = prod[16+CWD-1:16];
        nd    = 1;
        for (lvl = 0; lvl < LOG2N; lvl = lvl + 1) begin
            if (rr < node[2*nd]) begin
                nd = 2 * nd;
            end else begin
                rr = rr - node[2*nd];
                nd = 2 * nd + 1;
            end
        end
        idx = nd[LOG2N-1:0];
    end

    assign valid = |acc;
endmodule
// verilator lint_on UNUSEDSIGNAL
