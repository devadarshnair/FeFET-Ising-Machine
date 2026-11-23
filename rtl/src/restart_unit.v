// Stall counter and restart arms (P3.02; golden: scripts/golden/restart.py). arm: 0 none, 1 da_offset, 2 mesa, 3 kc2.
//   Stall counter: steps since the last improvement. mesa: improvement of the best-so-far feasible objective
//   (imp_best); kc2: improvement of the EPOCH best (ruling R1, the reference software study cpu.py). At K the machine restarts:
//   mesa  reload the best state (flip the differing spins one by one through the normal field/constraint update path),
//         then T := T0 and E_off := 0 (rs_sched_rst);
//   kc2   kick L distinct enabled spins of the current state (partial Fisher-Yates on a persistent permutation, draws
//         from the selection generator), no schedule reset unless rsched = 1; epoch best := f if feasible else -inf;
//         kc2_fin asks the controller for the best-so-far update with the kicked state.
// The restart runs between UPD and the next step in the controller state S_RST; rd/flip/idx drive the same read and
// update strobes as an ordinary flip (one flip = R_RD then R_FL, 2 cycles). The best-state shadow register is the
// controller's best_x (present for reporting in every arm; only MESA needs it for the restart).
// verilator lint_off WIDTHEXPAND   // 32 b objective extended into the 33 b epoch-best (sign) and integer loop bounds; values fit by construction
// verilator lint_off WIDTHTRUNC   // loop index i < N is narrowed to the LOG2N-bit lowest-differing-spin index
// verilator lint_off UNUSEDSIGNAL   // only the high product bits of rng_o * remain are the Fisher-Yates draw (fixed-point multiply); jsel[LOG2N] never used
module restart_unit #(
    parameter N     = 64,
    parameter LOG2N = $clog2(N),
    parameter MESA  = 1       // 0: Kc2-only build, the MESA best-state reload (N-wide differing-spin encoder) is removed; arm 2 then never triggers
) (
    input  wire                 clk,
    input  wire                 rst_n,
    input  wire                 init,        // run start: counters cleared
    // configuration
    input  wire [1:0]           arm,
    input  wire [31:0]          kcfg,
    input  wire [15:0]          lcfg,
    input  wire                 rsched,
    input  wire [N-1:0]         lane_en,
    // permutation initialisation (during the seeding cycles)
    input  wire                 seed_init,
    input  wire                 pinit,
    // step events from the controller (valid in the UPD cycle)
    input  wire                 upd,
    input  wire                 flipped_ok,  // a flip is applied and the state after it is feasible
    input  wire                 imp_best,    // that flip improves the best-so-far
    input  wire signed [31:0]   f_new,
    // state seen by the restart
    input  wire [N-1:0]         x,
    input  wire [N-1:0]         best_x,
    input  wire signed [31:0]   f,
    input  wire                 feas_now,
    input  wire [31:0]          rng_o,
    // outputs
    output wire                 trig,        // combinational in the UPD cycle: this step ends in a restart
    output wire                 rd,
    output wire                 flip,
    output wire [LOG2N-1:0]     idx,
    output wire                 gen_adv,
    output wire                 sched_rst,
    output wire                 kc2_fin,
    output wire                 fin,
    output reg  [31:0]          n_restart
);
    localparam [3:0] R_IDLE = 4'd0, R_CHK = 4'd1, R_DRAW = 4'd2, R_RD = 4'd3, R_FL = 4'd4, R_FIN = 4'd5, R_SWAP = 4'd6, R_ENC = 4'd7, R_ADD = 4'd8, R_SWP1 = 4'd9;

    reg  [31:0]        stall;
    reg  signed [32:0] epoch_best;
    reg  [3:0]         rs;
    reg  [LOG2N:0]     size;
    reg  [LOG2N:0]     scan;
    reg  [LOG2N:0]     a;
    reg  [LOG2N-1:0]   tgt;
    reg  [LOG2N:0]     remain_q;    // pipelined draw: size - a, updated when a changes (keeps the subtractor out of the multiplier path)
    reg  [32+LOG2N:0]  prod_q;      // rng_o * remain_q, registered in R_DRAW
    reg  [LOG2N-1:0]   jr;          // the Fisher-Yates partner index, registered in R_ADD
    reg  [LOG2N-1:0]   pa_q;        // perm[a], read in R_DRAW
    reg  [LOG2N-1:0]   low_q;       // mesa: lowest differing spin, registered in R_CHK
    reg                pv_q, pe_q;  // permutation initialisation pipeline: valid, lane enabled
    reg  [LOG2N-1:0]   ps_q;        // ... and the scan index
    reg  [LOG2N-1:0]   perm [0:N-1];

    wire is_mesa = (MESA != 0) && (arm == 2'd2);
    wire is_kc2  = (arm == 2'd3);
    wire [LOG2N:0] lcap  = (size == 0) ? {(LOG2N+1){1'b0}} : size - 1'b1;
    wire [LOG2N:0] leff  = (lcfg[15:LOG2N+1] != 0 || lcfg[LOG2N:0] > lcap) ? lcap : lcfg[LOG2N:0];

    wire imp_kc2 = flipped_ok && (f_new > epoch_best);
    wire imp     = is_mesa ? imp_best : imp_kc2;
    wire [31:0] stall_next = imp ? 32'd0 : stall + 32'd1;
    assign trig = upd && (is_mesa || is_kc2) && (stall_next >= kcfg);

    // lowest differing spin (mesa), two registered stages: per group of GW spins (any, first index) in R_ENC, then the group priority / select in R_CHK
    localparam GW = (N < 32) ? N : 32;
    localparam GL = $clog2(GW);
    localparam NG = N / GW;
    reg [NG-1:0]    gany_c, gany_q;
    reg [NG*GL-1:0] gfst_c, gfst_q;
    reg [LOG2N-1:0] low;
    reg             any;
    integer         gi, bi, gj;
    wire [N-1:0]    diff = x ^ best_x;
    always @(diff) begin
        for (gi = 0; gi < NG; gi = gi + 1) begin
            gany_c[gi] = 1'b0;
            gfst_c[gi*GL +: GL] = {GL{1'b0}};
            for (bi = GW - 1; bi >= 0; bi = bi - 1)
                if (diff[gi*GW + bi]) begin gany_c[gi] = 1'b1; gfst_c[gi*GL +: GL] = bi; end
        end
    end
    always @(posedge clk) begin
        gany_q <= gany_c;
        gfst_q <= gfst_c;
    end
    always @(gany_q or gfst_q) begin
        low = {LOG2N{1'b0}};
        any = 1'b0;
        for (gj = NG - 1; gj >= 0; gj = gj - 1)
            if (gany_q[gj]) begin any = 1'b1; low = gj * GW + gfst_q[gj*GL +: GL]; end
    end

    // Fisher-Yates draw, six registered steps per kick: R_DRAW prod_q = rng_o * (size - a) and the group read of perm[a]; R_ADD jr = a + prod_q >> 32, pa_q = perm[a];
    // R_SWP1 group read of perm[jr]; R_SWAP tgt = perm[jr]; R_RD the two permutation writes (and the coupling-memory read); R_FL the flip
    wire [32+LOG2N:0]  prod   = rng_o * remain_q;
    // two-stage permutation read (an N:1 multiplexer of LOG2N-bit words is the long path of this unit at N = 1024): a group stage registers the PG words
    // that share the high index bits (grp_q, loaded every cycle from index a in R_DRAW and from jr in R_SWP1), the word stage picks one with the low bits
    localparam PG  = (N >= 64) ? 32 : N;
    localparam LPG = $clog2(PG);
    localparam NPG = N / PG;
    reg  [PG*LOG2N-1:0] grp_q;
    wire [LOG2N-1:0]    rd_idx = (rs == R_DRAW) ? a[LOG2N-1:0] : jr;
    wire [LOG2N-1:0]    rd_hi  = (NPG > 1) ? (rd_idx >> LPG) : {LOG2N{1'b0}};
    integer             pi;
    always @(posedge clk)
        for (pi = 0; pi < PG; pi = pi + 1)
            grp_q[pi*LOG2N +: LOG2N] <= perm[rd_hi * PG + pi];
    wire [LOG2N-1:0]    wd_a  = grp_q[a[LPG-1:0] * LOG2N +: LOG2N];
    wire [LOG2N-1:0]    wd_jr = grp_q[jr[LPG-1:0] * LOG2N +: LOG2N];
    wire [LOG2N:0]     jsel   = a + prod_q[32+LOG2N:32];

    assign rd        = (rs == R_RD);
    assign flip      = (rs == R_FL);
    assign idx       = is_mesa ? low_q : tgt;
    assign gen_adv   = (rs == R_DRAW);
    assign fin       = (rs == R_FIN);
    assign sched_rst = fin && (is_mesa || (is_kc2 && rsched));
    assign kc2_fin   = fin && is_kc2;

    always @(posedge clk) begin
        if (!rst_n) begin
            rs        <= R_IDLE;
            n_restart <= 32'd0;
            size      <= 0;
            scan      <= 0;
        end else begin
            // permutation initialisation: enabled lanes in ascending order, two stages (lane_en[scan] is an N:1 multiplexer): stage A registers the
            // enable bit and the scan index, stage B appends the index to the permutation; pinit must stay high for N + 1 cycles
            if (seed_init) begin
                scan <= 0;
                size <= 0;
                pv_q <= 1'b0;
            end else begin
                pv_q <= pinit && scan < N;
                pe_q <= lane_en[scan[LOG2N-1:0]];
                ps_q <= scan[LOG2N-1:0];
                if (pinit && scan < N)
                    scan <= scan + 1'b1;
                if (pv_q && pe_q) begin
                    perm[size[LOG2N-1:0]] <= ps_q;
                    size <= size + 1'b1;
                end
            end
            if (init)
                n_restart <= 32'd0;
            case (rs)
                R_IDLE: if (trig) begin
                    a        <= 0;
                    remain_q <= size;
                    if (is_mesa)             rs <= R_ENC;
                    else if (leff == 0)      rs <= R_FIN;
                    else                     rs <= R_DRAW;
                end
                R_ENC:  rs <= R_CHK;
                R_CHK: begin
                    low_q <= low;
                    rs    <= any ? R_RD : R_FIN;
                end
                R_DRAW: begin
                    prod_q <= prod;
                    rs     <= R_ADD;
                end
                R_ADD: begin
                    jr   <= jsel[LOG2N-1:0];
                    pa_q <= wd_a;
                    rs   <= R_SWP1;
                end
                R_SWP1: rs <= R_SWAP;
                R_SWAP: begin
                    tgt <= wd_jr;
                    rs  <= R_RD;
                end
                R_RD: begin
                    if (!is_mesa) begin
                        perm[jr]              <= pa_q;
                        perm[a[LOG2N-1:0]]    <= tgt;
                    end
                    rs <= R_FL;
                end
                R_FL: begin
                    if (is_mesa) rs <= R_ENC;
                    else begin
                        a        <= a + 1'b1;
                        remain_q <= size - a - 1'b1;
                        rs       <= (a + 1'b1 == leff) ? R_FIN : R_DRAW;
                    end
                end
                R_FIN: begin
                    rs        <= R_IDLE;
                    n_restart <= n_restart + 1'b1;
                end
                default: rs <= R_IDLE;
            endcase
        end
    end

    // stall counter and epoch best
    always @(posedge clk) begin
        if (init) begin
            stall      <= 32'd0;
            epoch_best <= 33'sd0;
        end else begin
            if (upd) begin
                stall <= trig ? 32'd0 : stall_next;
                if (imp_kc2)
                    epoch_best <= f_new;
            end
            if (kc2_fin)
                epoch_best <= feas_now ? {f[31], f} : {1'b1, 32'd0};
        end
    end
endmodule
// verilator lint_on WIDTHEXPAND
// verilator lint_on WIDTHTRUNC
// verilator lint_on UNUSEDSIGNAL
