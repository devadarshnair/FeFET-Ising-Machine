// TIM v0 top level: TCAM-augmented parallel-trial Ising (QUBO) machine. Spec: docs/rtl/SPEC_v0.md.
// Host side: a write-only configuration bus (SPEC 6.1) and the TCAM write port (SPEC 6.2). Pulse start; the
// machine seeds its generators, runs K steps and raises done. The dbg_* outputs exist for the testbenches.
// verilator lint_off UNUSEDSIGNAL   // generator state: the low 64 b link to the neighbouring generator, the full state is only observable in tb; r_sg/r_nseed/bias_bus exist only for CIM = 1, r_tl_* only for TCL = 1
module tim_top #(
    parameter N          = 64,
    parameter NCON       = 8,
    parameter NLEV       = 8,
    parameter SEGW       = 64,
    parameter SEARCH_LAT = 2,
    parameter WRITE_LAT  = 4,
    parameter ERR_HOOK   = 1,
    parameter LAB        = 10,
    parameter CIM        = 0,
    parameter CIMLAT     = 1,
    parameter CIMNOISE   = 1,
    parameter CIMWB      = 8,
    parameter TCL        = 0,    // 1: build the optional TCAM-lite visited-state arm (P3.07); 0: none, no hardware
    parameter TLM        = 16,   // TCAM-lite ring rows
    parameter JW         = 10,   // coupling width (signed): |P| <= 511 (was 8 bit)
    parameter BW         = 12,   // bias width (signed): |d| <= 2047 (was 8 bit)
    parameter SEL_PIPE   = 0,    // 1: pipelined select tree (timing study v2, select_tree_pipe); 0: the single-cycle tree of v0
    parameter SEL_ADD_CUT  = 0,  // pipeline cuts after adder level k (bit k-1), see select_tree_pipe
    parameter SEL_WALK_CUT = 0,  // pipeline cuts after walk step j (bit j)
    parameter RNG_CG     = 1,    // 1: lane / selection generators on gated clocks (clk_gate), 0: free-running clock with enable (v0, timing study v1)
    parameter RS_MESA    = 1,    // 0: restart unit without the MESA reload (differing-spin encoder); only for Kc2 / none builds
    // derived, do not override
    parameter NSEG       = (NCON * NLEV + SEGW - 1) / SEGW,
    parameter SGW        = (NSEG > 1) ? $clog2(NSEG) : 1,
    parameter TW         = $clog2(NSEG * SEGW + 1)
) (
    input  wire                         clk,
    input  wire                         rst_n,
    // host configuration bus
    input  wire                         cfg_we,
    input  wire [23:0]                  cfg_addr,
    input  wire [31:0]                  cfg_wdata,
    // host TCAM write port
    input  wire                         tw_en,
    input  wire [$clog2(N)-1:0]         tw_row,
    input  wire [SGW-1:0]               tw_seg,
    input  wire [SEGW-1:0]              tw_bits,
    input  wire [SEGW-1:0]              tw_care,
    output wire                         tw_busy,
    // control and TCAM hooks
    input  wire                         start,
    output wire                         busy,
    output wire                         done,
    input  wire                         err_en,
    input  wire [15:0]                  err_thr,
    // per-step and debug outputs
    output wire                         step_valid,
    output wire [31:0]                  step_idx,
    output wire                         sel_valid,
    output wire [$clog2(N)-1:0]         sel_idx,
    output wire [$clog2(N):0]           nacc,
    output wire [31:0]                  obj,
    output wire [31:0]                  best_obj,
    output wire [31:0]                  best_step,
    output wire [23:0]                  eoff,
    output wire [31:0]                  temp,
    output wire [N-1:0]                 dbg_x,
    output wire [N-1:0]                 dbg_best_x,
    output wire [N-1:0]                 dbg_acc,
    output wire [N*18-1:0]              dbg_h,
    output wire [NCON*16-1:0]           dbg_load,
    output wire [N*TW-1:0]              dbg_cnt_add,
    output wire [N*TW-1:0]              dbg_cnt_rem,
    output wire                         dbg_ovf,
    output wire [31:0]                  tc_search,
    output wire [31:0]                  tc_write,
    output wire [31:0]                  tc_wdrop,
    output wire [31:0]                  tc_err,
    output wire [47:0]                  tc_rows_en,
    output wire [47:0]                  tc_cells,
    output wire [15:0]                  rs_cycles,
    output wire [15:0]                  cim_cycles,
    output wire                         arr_en,
    output wire                         adc_en,
    output wire [4:0]                   adc_bits_o,
    output wire [8*32-1:0]              act_cnt,
    output wire [31:0]                  n_restart,
    output wire [4*32-1:0]              tl_cnt     // TCAM-lite: search, write, hit, lockout-block counters (0 when TCL = 0)
);
    // ---------------------------------------------------------------- widths (SPEC section 3)
    localparam LOG2N = $clog2(N);
    function integer popc;     // set bits of the low `w` bits of v
        input integer v;
        input integer w;
        integer b;
        begin
            popc = 0;
            for (b = 0; b < w; b = b + 1) popc = popc + ((v >> b) & 1);
        end
    endfunction
    localparam SEL_LAT = SEL_PIPE ? 2 + popc(SEL_ADD_CUT, LOG2N) + popc(SEL_WALK_CUT, LOG2N - 1) : 1;   // cycles in state SEL
    localparam CW    = $clog2(SEGW + 1);
    localparam WW    = 6;
    localparam LDW   = 16;
    localparam HW    = 18;
    localparam LW    = 12;
    localparam EW    = 24;
    localparam DW    = (JW > BW) ? JW : BW;

    // ---------------------------------------------------------------- configuration registers
    wire [3:0]  region = cfg_addr[23:20];
    wire [19:0] off    = cfg_addr[19:0];

    reg        mode_knap, mode_geom;
    reg [31:0] r_t0, r_alpha, r_ksteps;
    reg [15:0] r_deoff, r_lam;
    reg [2:0]  r_gsh;
    reg [5:0]  r_wmax;
    reg [63:0] r_seed;
    reg [31:0] r_k;
    reg [1:0]  r_arm;
    reg [15:0] r_l;
    reg        r_rsched;
    reg [4:0]  r_adcb;
    reg [15:0] r_adcfs;                           // I7v2 ADC full scale (offset 32); 0 = N rows (v1)
    reg [15:0] r_sg;
    reg [31:0] r_nseed;
    reg        r_i10, r_i7;
    reg [15:0] r_kg, r_kp;
    reg [4:0]  r_bhi, r_blo;
    reg        r_tl_en;
    reg [15:0] r_tl_kw, r_tl_ll;
    reg        r_i11, r_i3, r_i5;                 // tweaks I11 greedy, I3 ramped penalty, I5 held/grouped noise (all off = v0)
    reg [15:0] r_lam_lo, r_rq, r_hold;
    reg [31:0] r_ramp, r_rr;
    reg [3:0]  r_glog;
    reg [N-1:0] lane_en;     // lane-enable mask (region 6, offset j = lane j); all lanes on after reset (FIXES R1)

    always @(posedge clk) begin
        if (!rst_n)
            lane_en <= {N{1'b1}};
        else if (cfg_we && region == 4'd6)
            lane_en[off[LOG2N-1:0]] <= cfg_wdata[0];
    end

    always @(posedge clk) begin
        if (!rst_n) begin
            mode_knap <= 1'b0;
            mode_geom <= 1'b0;
            r_t0      <= 32'd0;
            r_alpha   <= 32'd0;
            r_ksteps  <= 32'd0;
            r_deoff   <= 16'd0;
            r_lam     <= 16'd0;
            r_gsh     <= 3'd0;
            r_wmax    <= 6'd1;
            r_seed    <= 64'd0;
            r_k       <= 32'd0;
            r_arm     <= 2'd1;       // da_offset: the v0 machine
            r_l       <= 16'd10;
            r_rsched  <= 1'b0;
            r_adcb    <= 5'd16;
            r_adcfs   <= 16'd0;
            r_sg      <= 16'd0;
            r_nseed   <= 32'd0;
            r_i10     <= 1'b0;
            r_i7      <= 1'b0;
            r_kg      <= 16'd64;
            r_kp      <= 16'd32;
            r_bhi     <= 5'd16;
            r_blo     <= 5'd8;
            r_tl_en   <= 1'b0;
            r_tl_kw   <= 16'd16;
            r_tl_ll   <= 16'd8;
            r_i11     <= 1'b0;
            r_i3      <= 1'b0;
            r_i5      <= 1'b0;
            r_lam_lo  <= 16'd0;
            r_ramp    <= 32'd1;
            r_rq      <= 16'd0;
            r_rr      <= 32'd0;
            r_hold    <= 16'd1;
            r_glog    <= 4'd0;
        end else if (cfg_we && region == 4'd0) begin
            case (off)
                20'd0: begin mode_knap <= cfg_wdata[0]; mode_geom <= cfg_wdata[1]; end
                20'd1: r_t0           <= cfg_wdata;
                20'd2: r_alpha        <= cfg_wdata;
                20'd3: r_deoff        <= cfg_wdata[15:0];
                20'd4: r_lam          <= cfg_wdata[15:0];
                20'd5: r_gsh          <= cfg_wdata[2:0];
                20'd6: r_wmax         <= cfg_wdata[5:0];
                20'd7: r_seed[31:0]   <= cfg_wdata;
                20'd8: r_seed[63:32]  <= cfg_wdata;
                20'd9: r_ksteps       <= cfg_wdata;
                20'd10: r_k           <= cfg_wdata;
                20'd11: r_arm         <= cfg_wdata[1:0];
                20'd12: r_l           <= cfg_wdata[15:0];
                20'd13: r_rsched      <= cfg_wdata[0];
                20'd14: r_adcb        <= cfg_wdata[4:0];
                20'd15: r_sg          <= cfg_wdata[15:0];
                20'd16: r_nseed       <= cfg_wdata;
                20'd17: begin r_i10 <= cfg_wdata[0]; r_i7 <= cfg_wdata[1]; end
                20'd18: r_kg          <= cfg_wdata[15:0];
                20'd19: r_kp          <= cfg_wdata[15:0];
                20'd20: r_bhi         <= cfg_wdata[4:0];
                20'd21: r_blo         <= cfg_wdata[4:0];
                20'd22: r_tl_en       <= cfg_wdata[0];
                20'd23: r_tl_kw       <= cfg_wdata[15:0];
                20'd24: r_tl_ll       <= cfg_wdata[15:0];
                20'd25: begin r_i11 <= cfg_wdata[0]; r_i3 <= cfg_wdata[1]; r_i5 <= cfg_wdata[2]; end
                20'd26: r_lam_lo      <= cfg_wdata[15:0];
                20'd27: r_ramp        <= cfg_wdata;
                20'd28: r_rq          <= cfg_wdata[15:0];
                20'd29: r_rr          <= cfg_wdata;
                20'd30: r_hold        <= cfg_wdata[15:0];
                20'd31: r_glog        <= cfg_wdata[3:0];
                20'd32: r_adcfs       <= cfg_wdata[15:0];
                default: ;
            endcase
        end
    end

    wire wr_p   = cfg_we && region == 4'd1;
    wire wr_b   = cfg_we && region == 4'd2;
    wire wr_lut = cfg_we && region == 4'd3;
    wire wr_w   = cfg_we && region == 4'd4;
    wire wr_c   = cfg_we && region == 4'd5;
    // regions 1 and 4 use offset = j*N + k; regions 2 and 5 use offset = j
    wire [LOG2N-1:0] cm_row  = wr_b ? off[LOG2N-1:0] : off[2*LOG2N-1:LOG2N];
    wire [3:0]       cu_con  = wr_c ? off[3:0] : off[LOG2N+3:LOG2N];

    // ---------------------------------------------------------------- controller
    wire seed_init, seed_shift, init, qenc_ld, s_valid, s_rem, cnt_add_ld, cnt_rem_ld;
    wire acc_ld, sel_ld, rd_en, upd, flip;
    wire [3:0] st;
    wire sel_valid_c;
    wire [LOG2N-1:0] sel_idx_c;
    wire [LOG2N:0]   sel_cnt_c;
    wire signed [HW-1:0] gain_sel;
    wire feas_next, feas_now, cim_ld;
    wire pc_skip;
    wire [4:0] pc_bits;
    wire s_done;
    wire rs_trig, rs_fin, rs_rd, rs_flip, rs_gen_adv, rs_sched_rst, rs_kc2_fin, flipped_ok, imp_best;
    wire [LOG2N-1:0] rs_idx;
    wire signed [31:0] f_new;
    wire [N-1:0] x;
    wire signed [31:0] f, best_f;

    tim_ctrl #(.CIM(CIM), .N(N), .HW(HW), .SEL_LAT(SEL_LAT)) u_ctrl (
        .clk(clk), .rst_n(rst_n), .start(start), .knap(mode_knap), .ksteps(r_ksteps), .s_done(s_done),
        .sel_valid_c(sel_valid_c), .sel_idx_c(sel_idx_c), .sel_cnt_c(sel_cnt_c),
        .gain_sel(gain_sel), .x(x), .feas_next(feas_next), .feas_now(feas_now),
        .cim_dur(CIMLAT[5:0] + {1'b0, pc_bits}), .cim_skip_nx(pc_skip), .cim_ld(cim_ld), .cim_cycles(cim_cycles),
        .rs_trig(rs_trig), .rs_fin(rs_fin), .rs_flip(rs_flip), .rs_kc2_fin(rs_kc2_fin),
        .flipped_ok(flipped_ok), .imp_best(imp_best), .f_new_o(f_new), .rs_cycles(rs_cycles),
        .busy(busy), .done(done), .st(st),
        .seed_init(seed_init), .seed_shift(seed_shift), .init(init), .qenc_ld(qenc_ld), .s_valid(s_valid),
        .s_rem(s_rem), .cnt_add_ld(cnt_add_ld), .cnt_rem_ld(cnt_rem_ld), .acc_ld(acc_ld), .sel_ld(sel_ld),
        .rd_en(rd_en), .upd(upd), .flip(flip),
        .sel_valid(sel_valid), .sel_idx(sel_idx), .nacc(nacc), .step(step_idx), .step_valid(step_valid),
        .f(f), .best_f(best_f), .best_step(best_step), .best_x(dbg_best_x)
    );

    // ---------------------------------------------------------------- random numbers: N lanes + 1 selection
    // Generator g = 0..N-1 belongs to lane g, generator N is the selection generator. During SEED the states form
    // one shift chain {S_N, ..., S_0} that moves right by 64 bits per cycle, splitmix64 output entering at the top.
    wire [63:0] sm_out;
    splitmix64 u_seed (.clk(clk), .init(seed_init), .seed(r_seed), .next(seed_shift), .out(sm_out));

    // Lane generator advance (I11: never; I5: once per hold window)
    wire lane_adv;
    hold_ctl u_hold (.clk(clk), .init(init), .acc_ld(acc_ld), .i11(r_i11), .i5(r_i5), .hold(r_hold), .lane_adv(lane_adv));

    // Generator clocks. With RNG_CG every lane generator shares one gated clock (they advance together: seeding shift, or acc_ld with lane_adv; I11 never),
    // the selection generator has its own (seeding shift, sel_ld, restart draw): idle generators see no clock edge at all.
    wire gclk_lane, gclk_sel;
    generate
        if (RNG_CG != 0) begin : cg
            clk_gate u_lane (.clk(clk), .en(seed_shift | (acc_ld & lane_adv)), .gclk(gclk_lane));
            clk_gate u_sel  (.clk(clk), .en(seed_shift | sel_ld | rs_gen_adv), .gclk(gclk_sel));
        end else begin : nocg
            assign gclk_lane = clk;
            assign gclk_sel  = clk;
        end
    endgenerate

    genvar g;
    generate
        for (g = 0; g <= N; g = g + 1) begin : rng
            wire [127:0] gst;
            wire [31:0]  o;
            wire [63:0]  next_low;
            if (g == N) begin : top_end
                assign next_low = sm_out;
            end else begin : link
                assign next_low = rng[g+1].gst[63:0];
            end
            xoshiro128ss #(.GATED(RNG_CG)) u_x (
                .clk((g == N) ? gclk_sel : gclk_lane), .ld(seed_shift), .ld_state({next_low, gst[127:64]}),
                .adv((g == N) ? (sel_ld | rs_gen_adv) : (acc_ld & lane_adv)), .out(o), .state(gst)
            );
        end
    endgenerate

    // ---------------------------------------------------------------- spins
    // The restart unit reuses the ordinary read/flip path with its own index (rs_rd / rs_flip, FIDX).
    wire [LOG2N-1:0] fidx  = (rs_rd | rs_flip) ? rs_idx : sel_idx;
    wire             rd_m  = rd_en | rs_rd;
    wire             flp_m = flip | rs_flip;
    wire dir = ~x[fidx];             // 1: spin fidx goes 0 -> 1 (item added)
    spin_reg #(.N(N)) u_spin (.clk(clk), .clr(init), .flip(flp_m), .flip_idx(fidx), .x(x));

    // ---------------------------------------------------------------- constraints and the TCAM pricer
    wire [NCON*LDW-1:0]     load;
    wire [NCON*(LDW+1)-1:0] slack;
    constraint_unit #(.N(N), .NCON(NCON), .WW(WW), .LDW(LDW)) u_con (
        .clk(clk), .wr_w(wr_w), .wr_c(wr_c), .wr_con(cu_con), .wr_item(off[LOG2N-1:0]), .wr_data(cfg_wdata[15:0]),
        .clr(init), .rd_en(rd_m), .rd_item(fidx), .upd(flp_m), .dir(dir), .en(mode_knap),
        .load(load), .slack(slack), .feas_next(feas_next)
    );

    wire [NSEG*SEGW-1:0] add_mask, rem_mask;
    query_enc #(.NCON(NCON), .NLEV(NLEV), .SEGW(SEGW), .NSEG(NSEG), .LDW(LDW)) u_qenc (
        .clk(clk), .ld(qenc_ld), .slack(slack), .wmax(r_wmax), .add_mask(add_mask), .rem_mask(rem_mask)
    );

    wire [N*NSEG*CW-1:0] r_cnt;
    tcam_stub #(.NROW(N), .SEGW(SEGW), .NSEG(NSEG), .CW(CW), .SEARCH_LAT(SEARCH_LAT), .WRITE_LAT(WRITE_LAT),
                .ERR_HOOK(ERR_HOOK)) u_tcam (
        .clk(clk), .rst_n(rst_n),
        .wr_en(tw_en), .wr_row(tw_row), .wr_seg(tw_seg), .wr_bits(tw_bits), .wr_care(tw_care), .wr_busy(tw_busy),
        .s_valid(s_valid), .s_key({(NSEG*SEGW){1'b0}}), .s_mask(s_rem ? rem_mask : add_mask),
        .s_row_en(s_rem ? x : ~x), .s_done(s_done), .r_cnt(r_cnt),
        .err_en(err_en), .err_thr(err_thr),
        .n_search(tc_search), .n_write(tc_write), .n_wdrop(tc_wdrop), .n_err(tc_err),
        .n_rows_en(tc_rows_en), .n_cells(tc_cells)
    );

    // ---------------------------------------------------------------- lanes
    wire [EW-1:0]   eoff_w;
    wire [31:0]     temp_w;
    wire [N-1:0]    acc_c;
    wire [N*HW-1:0] gain;
    wire [N-1:0]    ovf_lane;
    reg  [N-1:0]    acc_q;
    wire [N-1:0]    tl_locked;
    generate
        if (TCL != 0) begin : tlite
            tcam_lite #(.N(N), .M(TLM)) u_tl (
                .clk(clk), .init(init), .en(r_tl_en), .kw(r_tl_kw), .llock(r_tl_ll), .step_end(step_valid),
                .k_valid(sel_valid), .k_idx(sel_idx), .x(x), .best_f(best_f), .acc_ld(acc_ld),
                .acc_pre(acc_c & lane_en), .locked(tl_locked),
                .n_search(tl_cnt[0*32 +: 32]), .n_write(tl_cnt[1*32 +: 32]), .n_hit(tl_cnt[2*32 +: 32]),
                .n_block(tl_cnt[3*32 +: 32])
            );
        end else begin : notl
            assign tl_locked = {N{1'b0}};
            assign tl_cnt    = {4*32{1'b0}};
        end
    endgenerate
    wire [N*HW-1:0] hcim;
    wire [N*BW-1:0] bias_bus;

    // I3: penalty weight register of the current step (host value r_lam when the ramp is off)
    wire [15:0] lam_t;
    lam_ramp u_ramp (
        .clk(clk), .init(init), .step(upd), .lam_lo(r_lam_lo), .ramp(r_ramp), .dq(r_rq), .dr(r_rr), .lam_t(lam_t)
    );
    wire [15:0] lam_eff = r_i3 ? lam_t : r_lam;

    genvar i;
    generate
        for (i = 0; i < N; i = i + 1) begin : lane
            wire [HW-1:0] h_i, gain_i, h_acc_i;
            wire [TW-1:0] ca_i, cr_i;
            // I5 lane groups: lanes of a group of 2^r_glog share the group leader's generator word
            wire [32*(LOG2N+1)-1:0] cand;
            genvar gk;
            for (gk = 0; gk <= LOG2N; gk = gk + 1) begin : grp
                assign cand[gk*32 +: 32] = rng[(i >> gk) << gk].o;
            end
            wire [31:0]   lane_rnd;
            lane_rnd_mux #(.LOG2N(LOG2N)) u_rm (.cand(cand), .glog(r_glog), .i5(r_i5), .rnd(lane_rnd));
            tim_lane #(.N(N), .NSEG(NSEG), .CW(CW), .TW(TW), .LAB(LAB), .LW(LW), .HW(HW), .EW(EW), .JW(JW), .BW(BW)) u_lane (
                .clk(clk),
                .wr_p(wr_p && cm_row == i), .wr_b(wr_b && cm_row == i), .wr_col(off[LOG2N-1:0]),
                .wr_data(cfg_wdata[DW-1:0]), .wr_lut(wr_lut), .wr_lut_addr(off[LAB-1:0]),
                .wr_lut_data(cfg_wdata[LW-1:0]),
                .init(init), .rd_en(rd_m), .rd_col(fidx), .flip(flp_m), .dir(dir),
                .cnt_add_ld(cnt_add_ld), .cnt_rem_ld(cnt_rem_ld), .seg_cnt(r_cnt[i*NSEG*CW +: NSEG*CW]),
                .x(x[i]), .h_acc(h_acc_i), .lam(lam_eff), .gsh(r_gsh), .eoff(eoff_w), .temp(temp_w), .rnd(lane_rnd), .greedy(r_i11),
                .h(h_i), .bias_o(bias_bus[i*BW +: BW]), .gain(gain_i), .acc(acc_c[i]), .cnt_add(ca_i), .cnt_rem(cr_i), .ovf(ovf_lane[i])
            );
            assign h_acc_i = (CIM != 0) ? hcim[i*HW +: HW] : h_i;
            assign gain[i*HW +: HW]        = gain_i;
            assign dbg_h[i*HW +: HW]       = h_i;
            assign dbg_cnt_add[i*TW +: TW] = ca_i;
            assign dbg_cnt_rem[i*TW +: TW] = cr_i;
        end
    endgenerate

    generate
        if (CIM != 0) begin : cimarr
            cim_field_unit #(.N(N), .WB(CIMWB), .JW(JW), .BW(BW), .NOISE(CIMNOISE), .HW(HW)) u_cim (
                .clk(clk), .wr_p(wr_p), .wr_row(cm_row), .wr_col(off[LOG2N-1:0]), .wr_val(cfg_wdata[JW-1:0]),
                .ld_seed(seed_init), .seed(r_nseed), .sg(r_sg), .adc_bits(pc_bits), .adc_fs(r_adcfs), .x(x), .d(bias_bus),
                .ld(cim_ld), .h(hcim)
            );
        end else begin : nocim
            assign hcim = {N*HW{1'b0}};
        end
    endgenerate

    always @(posedge clk) begin
        if (init)
            acc_q <= {N{1'b0}};
        else if (acc_ld)
            acc_q <= acc_c & lane_en & ~tl_locked;     // padding lanes never accept; TCAM-lite lockout
    end

    // ---------------------------------------------------------------- selection, offset, temperature
    generate if (SEL_PIPE != 0) begin : g_selp
        select_tree_pipe #(.N(N), .ADD_CUT(SEL_ADD_CUT), .WALK_CUT(SEL_WALK_CUT)) u_sel (
            .clk(clk), .acc(acc_q), .r16(rng[N].o[31:16]), .valid(sel_valid_c), .idx(sel_idx_c), .count(sel_cnt_c)
        );
    end else begin : g_sel1
        select_tree #(.N(N)) u_sel (
            .acc(acc_q), .r16(rng[N].o[31:16]), .valid(sel_valid_c), .idx(sel_idx_c), .count(sel_cnt_c)
        );
    end endgenerate

    assign gain_sel = gain[fidx*HW +: HW];

    wire [NCON-1:0] slack_neg;
    genvar sj;
    generate
        for (sj = 0; sj < NCON; sj = sj + 1) begin : sneg
            assign slack_neg[sj] = slack[sj*(LDW+1) + LDW];
        end
    endgenerate
    assign feas_now = ~mode_knap | ~(|slack_neg);

    wire kc2_best_upd = rs_kc2_fin && feas_now && (f > best_f);
    power_ctl #(.N(N)) u_pc (
        .clk(clk), .rst_n(rst_n), .init(init), .i10(r_i10), .i7(r_i7), .kg(r_kg), .kp(r_kp), .b_hi(r_bhi),
        .b_lo(r_blo), .b_nom(r_adcb), .upd(upd), .sel_valid(sel_valid), .trig(rs_trig), .fin(rs_fin),
        .imp_best(imp_best), .kc2_best_upd(kc2_best_upd), .acc_ld(acc_ld), .cim_ld(cim_ld),
        .cim_busy(st == 4'd14), .skip_nx(pc_skip), .arr_en(arr_en), .adc_en(adc_en), .adc_bits(pc_bits),
        .c_reads(act_cnt[0*32 +: 32]), .c_skipped(act_cnt[1*32 +: 32]), .c_cells(act_cnt[2*32 +: 32]),
        .c_conv(act_cnt[3*32 +: 32]), .c_convbits(act_cnt[4*32 +: 32]), .c_lowc(act_cnt[5*32 +: 32]),
        .c_lowb(act_cnt[6*32 +: 32]), .c_gated(act_cnt[7*32 +: 32])
    );
    assign adc_bits_o = pc_bits;

    restart_unit #(.N(N), .MESA(RS_MESA)) u_rs (
        .clk(clk), .rst_n(rst_n), .init(init), .arm(r_arm), .kcfg(r_k), .lcfg(r_l), .rsched(r_rsched),
        .lane_en(lane_en), .seed_init(seed_init), .pinit(seed_shift), .upd(upd), .flipped_ok(flipped_ok),
        .imp_best(imp_best), .f_new(f_new), .x(x), .best_x(dbg_best_x), .f(f), .feas_now(feas_now),
        .rng_o(rng[N].o), .trig(rs_trig), .rd(rs_rd), .flip(rs_flip), .idx(rs_idx), .gen_adv(rs_gen_adv),
        .sched_rst(rs_sched_rst), .kc2_fin(rs_kc2_fin), .fin(rs_fin), .n_restart(n_restart)
    );

    offset_unit #(.EW(EW)) u_off (
        .clk(clk), .clr(init | rs_sched_rst), .upd(upd), .accepted(sel_valid),
        .deoff((r_arm == 2'd0 || r_i11) ? 16'd0 : r_deoff), .eoff(eoff_w)
    );

    temp_sched u_temp (
        .clk(clk), .load(init | rs_sched_rst), .t0(r_t0), .step(upd & ~r_i11), .geom(mode_geom), .alpha(r_alpha), .temp(temp_w)
    );

    // ---------------------------------------------------------------- outputs
    assign obj      = f;
    assign best_obj = best_f;
    assign eoff     = eoff_w;
    assign temp     = temp_w;
    assign dbg_x    = x;
    assign dbg_acc  = acc_q;
    assign dbg_load = load;
    assign dbg_ovf  = |ovf_lane;
endmodule
// verilator lint_on UNUSEDSIGNAL
