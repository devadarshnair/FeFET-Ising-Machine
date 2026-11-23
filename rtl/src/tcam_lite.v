// TCAM-lite visited-state arm (P3.07; golden: scripts/golden/tcam_lite.py, P2.05). Optional, off by default
// (tim_top parameter TCL = 0 builds none of this; run-time enable bit en = 0 leaves the machine unchanged).
// Match/miss only. A ring of M exact-match rows holds visited states (N bits each).
//   stall counter: consecutive steps without a strict improvement of best_f; while it is a positive multiple of
//   kw the state after the step is written into the next ring row (after the search of the same step).
//   After every step that flipped a lane (k_valid) the state after the step is searched; an exact hit starts a
//   lockout of llock steps on the lane that just flipped (locked[k] = 1: the lane may not be accepted).
// Strobe step_end is the controller's step_valid (x, best_f are final for the step, restart included). It is
// modelled as combinational parallel logic: no cycles are added to a step (the cost model charges search/write
// energy from the exported counters).
// verilator lint_off WIDTHEXPAND   // ring pointer compared with the integer constant M - 1
module tcam_lite #(
    parameter N  = 64,
    parameter M  = 16,
    parameter LN = $clog2(N)
) (
    input  wire                 clk,
    input  wire                 init,
    input  wire                 en,
    input  wire [15:0]          kw,
    input  wire [15:0]          llock,
    input  wire                 step_end,
    input  wire                 k_valid,
    input  wire [LN-1:0]        k_idx,
    input  wire [N-1:0]         x,
    input  wire signed [31:0]   best_f,
    input  wire                 acc_ld,
    input  wire [N-1:0]         acc_pre,
    output wire [N-1:0]         locked,
    output reg  [31:0]          n_search,
    output reg  [31:0]          n_write,
    output reg  [31:0]          n_hit,
    output reg  [31:0]          n_block
);
    localparam MW = (M > 1) ? $clog2(M) : 1;

    reg [M*N-1:0] rows;       // packed: row r at [r*N +: N]
    reg [M-1:0]  valid;
    reg [MW-1:0] ptr;
    reg [15:0]   stall;           // stalled steps since the last improvement or write
    reg signed [31:0] last_best;
    reg [15:0]   lock_cnt [0:N-1];

    genvar g;
    generate
        for (g = 0; g < N; g = g + 1) begin : lk
            assign locked[g] = en && (lock_cnt[g] != 16'd0);
        end
    endgenerate

    reg hit;
    integer r;
    always @* begin
        hit = 1'b0;
        for (r = 0; r < M; r = r + 1)
            if (valid[r] && rows[r*N +: N] == x) hit = 1'b1;
    end

    wire improved   = best_f > last_best;
    wire [15:0] st_nx = improved ? 16'd0 : stall + 16'd1;
    wire do_write   = en && !improved && (kw != 16'd0) && (st_nx == kw);   // kw = 0: never write (no 16-bit wrap hit)
    wire do_search  = en && k_valid;
    wire do_hit     = do_search && hit;

    integer j;
    always @(posedge clk) begin
        if (init) begin
            valid     <= {M{1'b0}};
            ptr       <= {MW{1'b0}};
            stall     <= 16'd0;
            last_best <= 32'sd0;
            n_search  <= 32'd0;
            n_write   <= 32'd0;
            n_hit     <= 32'd0;
            n_block   <= 32'd0;
            for (j = 0; j < N; j = j + 1) lock_cnt[j] <= 16'd0;
        end else begin
            if (acc_ld && en && (acc_pre & locked) != {N{1'b0}})
                n_block <= n_block + 32'd1;
            if (step_end && en) begin
                last_best <= best_f;
                stall     <= do_write ? 16'd0 : st_nx;
                for (j = 0; j < N; j = j + 1)
                    if (lock_cnt[j] != 16'd0) lock_cnt[j] <= lock_cnt[j] - 16'd1;
                if (do_search) n_search <= n_search + 32'd1;
                if (do_hit) begin
                    n_hit <= n_hit + 32'd1;
                    lock_cnt[k_idx] <= llock;
                end
                if (do_write) begin
                    rows[ptr*N +: N] <= x;
                    valid[ptr] <= 1'b1;
                    ptr        <= (ptr == M - 1) ? {MW{1'b0}} : ptr + 1'b1;
                    n_write    <= n_write + 32'd1;
                end
            end
        end
    end
endmodule
// verilator lint_on WIDTHEXPAND
