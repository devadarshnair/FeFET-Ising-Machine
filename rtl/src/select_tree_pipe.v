// Pipelined version of select_tree (timing study v2). Same function, same result: the selected lane for a held (acc, r16) is
// bit-identical to select_tree; only the latency differs. The inputs (acc, r16) must stay constant for the whole latency
// (tim_ctrl holds state SEL for SEL_LAT cycles; acc_q changes only in ACC and the selection generator advances only at
// the last SEL cycle), so the stages are plain registers, no valid/ready control is needed.
//
// Operation order: add level k = 1..LOG2N (k = 1 sums leaf pairs, k = LOG2N is the root count), then one multiply
// (rr = (r16 * count) >> 16), then walk step j = 0..LOG2N-1 (root first). A pipeline register is placed
//   after add level k        if ADD_CUT[k-1]   (k = 1..LOG2N)
//   after the multiply       always
//   after walk step j        if WALK_CUT[j]    (j = 0..LOG2N-2)
// LAT = 2 + popcount(ADD_CUT) + popcount(WALK_CUT) cycles from the held inputs to the valid outputs (outputs are combinational
// from the last stage; the consumer registers them in the last cycle). Every adder level is also kept in its own register
// copy (q) because the walk of a later stage reads all lower levels; the walk reads only registered copies.
// Width of a node at depth d (root d = 0): LOG2N - d + 1 bits (exactly what its count can need), so no constant-zero flops.
// verilator lint_off UNUSEDSIGNAL   // the low 16 bits of r16 * count are the fraction of the fixed-point multiply
module select_tree_pipe #(
    parameter N        = 64,
    parameter LOG2N    = $clog2(N),
    parameter ADD_CUT  = 0,
    parameter WALK_CUT = 0
) (
    input  wire             clk,
    input  wire [N-1:0]     acc,
    input  wire [15:0]      r16,
    output wire             valid,
    output wire [LOG2N-1:0] idx,
    output wire [LOG2N:0]   count
);
    localparam CWD = LOG2N + 1;

    // ---- adder tree: depth d holds 2^d counts of width W(d) = LOG2N - d + 1 (c = combinational sum, q = register copy,
    //      u = value seen by the next level up: the register copy when a cut follows this level, else the sum)
    genvar d, j;
    generate for (d = LOG2N; d >= 0; d = d - 1) begin : lv
        localparam W   = LOG2N - d + 1;
        localparam CUT = (d == LOG2N) ? 0 : ((ADD_CUT >> (LOG2N - d - 1)) & 1);
        wire [W*(1<<d)-1:0] c;
        wire [W*(1<<d)-1:0] u;
        wire [W*(1<<d)-1:0] q;
        if (d == LOG2N) begin : leaf
            assign c = acc;
            assign q = acc;
            assign u = acc;
        end else begin : sum
            reg [W*(1<<d)-1:0] qr;
            genvar i;
            for (i = 0; i < (1 << d); i = i + 1) begin : n
                assign c[i*W +: W] = {1'b0, lv[d+1].u[(2*i)*(W-1) +: (W-1)]} + {1'b0, lv[d+1].u[(2*i+1)*(W-1) +: (W-1)]};
            end
            always @(posedge clk) qr <= c;
            assign q = qr;
            assign u = (CUT != 0) ? qr : c;
        end
    end endgenerate

    assign count = lv[0].q;
    assign valid = |acc;

    // ---- multiply, always registered
    wire [CWD-1:0]       root = (LOG2N == 0) ? {CWD{1'b0}} : (((ADD_CUT >> (LOG2N - 1)) & 1) != 0) ? lv[0].q : lv[0].c;
    wire [16+CWD-1:0]    prod = r16 * root;
    reg  [CWD-1:0]       rr0q;
    always @(posedge clk) rr0q <= prod[16+CWD-1:16];

    // ---- walk: step j picks between the left child (depth j+1, position 2*ix) and the right one
    wire [CWD-1:0]    rr_c [0:LOG2N];
    wire [LOG2N-1:0]  ix_c [0:LOG2N];
    reg  [CWD-1:0]    rr_q [0:LOG2N];
    reg  [LOG2N-1:0]  ix_q [0:LOG2N];
    assign rr_c[0] = rr0q;
    assign ix_c[0] = {LOG2N{1'b0}};
    generate for (j = 0; j < LOG2N; j = j + 1) begin : wk
        localparam W    = LOG2N - j;          // width of a depth j+1 node
        localparam PREV = (j == 0) ? 0 : ((WALK_CUT >> (j - 1)) & 1);
        wire [CWD-1:0]   rr_in = (j == 0 || PREV == 0) ? rr_c[j] : rr_q[j];
        wire [LOG2N-1:0] ix_in = (j == 0 || PREV == 0) ? ix_c[j] : ix_q[j];
        wire [W-1:0]     left  = lv[j+1].q[(ix_in * 2) * W +: W];
        wire             goleft = (rr_in < {{(CWD-W){1'b0}}, left});
        assign rr_c[j+1] = goleft ? rr_in : rr_in - {{(CWD-W){1'b0}}, left};
        assign ix_c[j+1] = (ix_in << 1) | {{(LOG2N-1){1'b0}}, !goleft};
        always @(posedge clk) begin
            rr_q[j+1] <= rr_c[j+1];
            ix_q[j+1] <= ix_c[j+1];
        end
    end endgenerate
    assign idx = ix_c[LOG2N];
endmodule
// verilator lint_on UNUSEDSIGNAL
