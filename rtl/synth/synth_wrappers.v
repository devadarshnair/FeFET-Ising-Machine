// Synthesis-only wrappers (P3.09): isolate small structures that live inside larger RTL modules so that their gate
// counts can be reported alone. They are NOT part of the simulated design; each mirrors the cited RTL lines.

// Mirrors restart_unit.v lines 68-69 and 149-156: 32 b stall counter, clear on improvement or trigger, compare >= K.
module syn_stall_counter (
    input  wire        clk,
    input  wire        init,
    input  wire        upd,
    input  wire        imp,
    input  wire [31:0] kcfg,
    output wire        trig
);
    reg  [31:0] stall;
    wire [31:0] stall_next = imp ? 32'd0 : stall + 32'd1;
    assign trig = upd && (stall_next >= kcfg);
    always @(posedge clk) begin
        if (init) stall <= 32'd0;
        else if (upd) stall <= trig ? 32'd0 : stall_next;
    end
endmodule

// Mirrors tim_ctrl.v best_x (lines 149, 180, 189): N-bit best-state shadow register, synchronous clear, load enable.
module syn_shadow_reg #(
    parameter N = 64
) (
    input  wire         clk,
    input  wire         init,
    input  wire         ld,
    input  wire [N-1:0] d,
    output reg  [N-1:0] q
);
    always @(posedge clk) begin
        if (init) q <= {N{1'b0}};
        else if (ld) q <= d;
    end
endmodule

// tim_lane without its two storage arrays (coupling_mem, accept_lut): field unit, segment adder, count registers and
// the acceptance datapath. pk, bias and lval come from the arrays and are inputs here (same glue as tim_lane.v).
module syn_lane_logic #(
    parameter NSEG = 1,
    parameter CW   = 7,
    parameter TW   = 7,
    parameter LW   = 12,
    parameter HW   = 18,
    parameter EW   = 24,
    parameter JW   = 10,
    parameter BW   = 12
) (
    input  wire               clk,
    input  wire               init,
    input  wire               flip,
    input  wire               dir,
    input  wire               cnt_add_ld,
    input  wire               cnt_rem_ld,
    input  wire [NSEG*CW-1:0] seg_cnt,
    input  wire               x,
    input  wire [HW-1:0]      h_acc,
    input  wire [15:0]        lam,
    input  wire [2:0]         gsh,
    input  wire [EW-1:0]      eoff,
    input  wire [31:0]        temp,
    input  wire [JW-1:0]      pk,
    input  wire [BW-1:0]      bias,
    input  wire [LW-1:0]      lval,
    output wire [HW-1:0]      h,
    output wire [HW-1:0]      gain,
    output wire               acc,
    output reg  [TW-1:0]      cnt_add,
    output reg  [TW-1:0]      cnt_rem,
    output wire               ovf
);
    field_unit #(.JW(JW), .BW(BW), .HW(HW)) u_field (
        .clk(clk), .init(init), .bias(bias), .upd(flip), .dir(dir), .pk(pk), .h(h), .ovf(ovf)
    );
    wire [TW-1:0] tot;
    seg_adder #(.NROW(1), .NSEG(NSEG), .CW(CW), .TW(TW)) u_sum (.r_cnt(seg_cnt), .tot(tot));
    always @(posedge clk) begin
        if (init) begin
            cnt_add <= {TW{1'b0}};
            cnt_rem <= {TW{1'b0}};
        end else begin
            if (cnt_add_ld) cnt_add <= tot;
            if (cnt_rem_ld) cnt_rem <= tot;
        end
    end
    accept_unit #(.HW(HW), .TW(TW), .LW(LW), .EW(EW)) u_acc (
        .h(h), .h_acc(h_acc), .x(x), .cnt_add(cnt_add), .cnt_rem(cnt_rem), .lam(lam), .gsh(gsh), .eoff(eoff),
        .temp(temp), .lval(lval), .greedy(1'b0), .gain(gain), .acc(acc)
    );
endmodule

// P3.11: synthesis-only restructuring of select_tree (same ports, same function). The behavioural select_tree indexes
// node[2*nd] with a run-time nd, so every level becomes a mux over all 2N-1 nodes and ABC does not finish at N = 256.
// Here level lvl only muxes over its own 2^lvl nodes (path bits p), giving O(N) mux size. Equivalence with select_tree
// is checked by simulation (rtl/synth/tb_select_eq.v, exhaustive-random vectors at N = 64 and 256).
module syn_select_tree_lvl #(
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
    reg [CWD-1:0]     rr, lc;
    reg [LOG2N-1:0]   p;
    integer           i, lvl, k;

    always @(acc or r16) begin
        for (i = 0; i < N; i = i + 1)
            node[N+i] = {{(CWD-1){1'b0}}, acc[i]};
        for (i = N - 1; i >= 1; i = i - 1)
            node[i] = node[2*i] + node[2*i+1];
        count = node[1];
        prod  = r16 * node[1];
        rr    = prod[16+CWD-1:16];
        p     = 0;
        for (lvl = 0; lvl < LOG2N; lvl = lvl + 1) begin
            // left child of node (2^lvl + p) is 2^(lvl+1) + 2p; select among the 2^lvl candidates at this level
            lc = 0;
            for (k = 0; k < (1 << lvl); k = k + 1)
                if (p == k) lc = node[(2 << lvl) + 2*k];
            if (rr < lc) p = 2*p;
            else begin rr = rr - lc; p = 2*p + 1; end
        end
        idx = p;
    end
    assign valid = |acc;
endmodule

// P3.12 (partitioned select_tree for N = 4*PN): ABC cannot finish the monolithic N = 256 tree, so the same function is
// built from synthesisable sub-blocks that are synthesised separately and summed: 4 x syn_sel_cnt (subtree popcount),
// syn_sel_glue (count adder, r16*count multiplier, 2-level walk over the 4 subtree counts, 4:1 acc mux) and one
// syn_sel_walk (rank walk inside the chosen PN-bit subtree; recomputes that subtree's popcount tree).
// Equal to select_tree at N = 256 (rtl/synth/tb_select_eq.v, instance syn_select_tree_part).
module syn_sel_cnt #(
    parameter N = 64,
    parameter CW = $clog2(N) + 1
) (
    input  wire [N-1:0]  acc,
    output reg  [CW-1:0] count
);
    reg [CW-1:0] node [1:2*N-1];
    integer i;
    always @(acc) begin
        for (i = 0; i < N; i = i + 1) node[N+i] = {{(CW-1){1'b0}}, acc[i]};
        for (i = N - 1; i >= 1; i = i - 1) node[i] = node[2*i] + node[2*i+1];
        count = node[1];
    end
endmodule

module syn_sel_walk #(
    parameter N = 64,
    parameter LOG2N = $clog2(N),
    parameter CW = LOG2N + 1
) (
    input  wire [N-1:0]     acc,
    input  wire [CW-1:0]    rr_in,
    output reg  [LOG2N-1:0] idx
);
    reg [CW-1:0] node [1:2*N-1];
    reg [CW-1:0] rr;
    reg [CW:0]   nd;
    integer i, lvl;
    always @(acc or rr_in) begin
        for (i = 0; i < N; i = i + 1) node[N+i] = {{(CW-1){1'b0}}, acc[i]};
        for (i = N - 1; i >= 1; i = i - 1) node[i] = node[2*i] + node[2*i+1];
        rr = rr_in;
        nd = 1;
        for (lvl = 0; lvl < LOG2N; lvl = lvl + 1) begin
            if (rr < node[2*nd]) nd = 2 * nd;
            else begin rr = rr - node[2*nd]; nd = 2 * nd + 1; end
        end
        idx = nd[LOG2N-1:0];
    end
endmodule

// glue for 4 parts of PN bits (counts of PN+1 values need PCW bits), total N = 4*PN
module syn_sel_glue #(
    parameter PN = 64,
    parameter PCW = $clog2(PN) + 1,
    parameter CWT = PCW + 2
) (
    input  wire [4*PN-1:0]  acc,
    input  wire [15:0]      r16,
    input  wire [4*PCW-1:0] cnt4,
    output wire [CWT-1:0]   count,
    output reg  [1:0]       sel,
    output reg  [PCW-1:0]   rr_sub,
    output reg  [PN-1:0]    acc_sel
);
    wire [PCW-1:0] c0 = cnt4[0*PCW +: PCW], c1 = cnt4[1*PCW +: PCW], c2 = cnt4[2*PCW +: PCW], c3 = cnt4[3*PCW +: PCW];
    wire [CWT-1:0] l  = c0 + c1;
    wire [CWT-1:0] r  = c2 + c3;
    assign count = l + r;
    wire [16+CWT-1:0] prod = r16 * count;
    reg  [CWT-1:0] rr;
    always @* begin
        rr = prod[16+CWT-1:16];
        if (rr < l) begin
            sel = 0;
            if (rr < c0) rr_sub = rr; else begin sel = 1; rr_sub = rr - c0; end
        end else begin
            rr = rr - l;
            sel = 2;
            if (rr < c2) rr_sub = rr; else begin sel = 3; rr_sub = rr - c2; end
        end
        acc_sel = acc[sel*PN +: PN];
    end
endmodule

module syn_select_tree_part #(
    parameter N = 256,
    parameter PN = N / 4,
    parameter LOG2N = $clog2(N),
    parameter PCW = $clog2(PN) + 1
) (
    input  wire [N-1:0]     acc,
    input  wire [15:0]      r16,
    output wire             valid,
    output wire [LOG2N-1:0] idx,
    output wire [LOG2N:0]   count
);
    wire [4*PCW-1:0] cnt4;
    genvar g;
    generate for (g = 0; g < 4; g = g + 1) begin : parts
        syn_sel_cnt #(.N(PN)) u (.acc(acc[g*PN +: PN]), .count(cnt4[g*PCW +: PCW]));
    end endgenerate
    wire [1:0] sel; wire [PCW-1:0] rr_sub; wire [PN-1:0] acc_sel; wire [$clog2(PN)-1:0] sub;
    syn_sel_glue #(.PN(PN)) u_glue (.acc(acc), .r16(r16), .cnt4(cnt4), .count(count), .sel(sel), .rr_sub(rr_sub), .acc_sel(acc_sel));
    syn_sel_walk #(.N(PN)) u_walk (.acc(acc_sel), .rr_in(rr_sub), .idx(sub));
    assign idx = {sel, sub};
    assign valid = |acc;
endmodule
