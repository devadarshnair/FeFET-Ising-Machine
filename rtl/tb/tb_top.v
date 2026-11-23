// Top-level testbench: loads a host write script (.cfg, SPEC 9.2), runs the machine, and writes the per-step
// trace (SPEC 9.3) for comparison with the golden model. It also checks the cycles per step on every step.
// Plusargs: +cfg=<file> +trace=<file> [+maxcyc=<n>]. Parameters are set with iverilog -P.
// Summary line: "TB_TOP steps=... cps_err=... ovf=... searches=... writes=... wdrop=... ..." then
// "TB_TOP_END ok" or "TB_TOP_END fail <reason>".
module tb_top;
    parameter N          = 64;
    parameter NCON       = 8;
    parameter NLEV       = 8;
    parameter SEARCH_LAT = 2;
    parameter LAB        = 10;
    parameter CIM        = 0;
    parameter CIMWB      = 8;
    parameter TCL        = 0;
    parameter TLM        = 16;
    parameter SEL_PIPE   = 0;
    parameter SEL_ADD_CUT  = 0;
    parameter SEL_WALK_CUT = 0;
    parameter RS_MESA    = 1;
    parameter RNG_CG     = 1;

    localparam LOG2N = $clog2(N);
    localparam NSEG  = (NCON * NLEV + 63) / 64;
    localparam SGW   = (NSEG > 1) ? $clog2(NSEG) : 1;
    localparam TW    = $clog2(NSEG * 64 + 1);

    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg              rst_n = 1'b0;
    reg              cfg_we = 1'b0;
    reg [23:0]       cfg_addr = 24'd0;
    reg [31:0]       cfg_wdata = 32'd0;
    reg              tw_en = 1'b0;
    reg [LOG2N-1:0]  tw_row = {LOG2N{1'b0}};
    reg [SGW-1:0]    tw_seg = {SGW{1'b0}};
    reg [63:0]       tw_bits = 64'd0;
    reg [63:0]       tw_care = 64'd0;
    reg              start = 1'b0;
    wire             tw_busy, busy, done;

    wire             step_valid, sel_valid, ovf;
    wire [31:0]      step_idx, obj, best_obj, best_step, temp;
    wire [LOG2N-1:0] sel_idx;
    wire [LOG2N:0]   nacc;
    wire [23:0]      eoff;
    wire [N-1:0]     x, best_x, acc;
    wire [N*18-1:0]  h;
    wire [NCON*16-1:0] load;
    wire [N*TW-1:0]  cadd, crem;
    wire [31:0]      tc_search, tc_write, tc_wdrop, tc_err;
    wire [47:0]      tc_rows_en, tc_cells;
    wire [15:0]      rs_cycles, cim_cycles;
    wire             arr_en, adc_en;
    wire [4:0]       adc_bits_o;
    wire [255:0]     act_cnt;
    wire [31:0]      n_restart;
    wire [127:0]     tl_cnt;

    tim_top #(.N(N), .NCON(NCON), .NLEV(NLEV), .SEARCH_LAT(SEARCH_LAT), .LAB(LAB), .CIM(CIM), .CIMWB(CIMWB), .TCL(TCL), .TLM(TLM),
                .SEL_PIPE(SEL_PIPE), .SEL_ADD_CUT(SEL_ADD_CUT), .SEL_WALK_CUT(SEL_WALK_CUT), .RS_MESA(RS_MESA), .RNG_CG(RNG_CG)) dut (
        .clk(clk), .rst_n(rst_n), .cfg_we(cfg_we), .cfg_addr(cfg_addr), .cfg_wdata(cfg_wdata),
        .tw_en(tw_en), .tw_row(tw_row), .tw_seg(tw_seg), .tw_bits(tw_bits), .tw_care(tw_care), .tw_busy(tw_busy),
        .start(start), .busy(busy), .done(done), .err_en(1'b0), .err_thr(16'd0),
        .step_valid(step_valid), .step_idx(step_idx), .sel_valid(sel_valid), .sel_idx(sel_idx), .nacc(nacc),
        .obj(obj), .best_obj(best_obj), .best_step(best_step), .eoff(eoff), .temp(temp),
        .dbg_x(x), .dbg_best_x(best_x), .dbg_acc(acc), .dbg_h(h), .dbg_load(load), .dbg_cnt_add(cadd),
        .dbg_cnt_rem(crem), .dbg_ovf(ovf), .tc_search(tc_search), .tc_write(tc_write), .tc_wdrop(tc_wdrop),
        .tc_err(tc_err), .tc_rows_en(tc_rows_en), .tc_cells(tc_cells), .rs_cycles(rs_cycles), .cim_cycles(cim_cycles), .arr_en(arr_en), .adc_en(adc_en), .adc_bits_o(adc_bits_o), .act_cnt(act_cnt),
        .n_restart(n_restart), .tl_cnt(tl_cnt)
    );

    // ------------------------------------------------------------ cycle counter and per-step trace
    reg [31:0] cyc = 32'd0;
    always @(posedge clk) cyc <= cyc + 32'd1;

    integer    fd_tr = 0;
    integer    fd_act = 0, fd_rs = 0;
    reg [255:0] act_prev = 256'd0;
    reg [31:0]  act_d0, act_d1, act_d2, act_d3, act_d4, act_d5, act_d6, act_d7;
    integer    i;
    integer    nsteps = 0;
    integer    cps_err = 0;
    reg [31:0] last_cyc, cps_expect, hcs, acs, lcs, ccs, hv;

    always @(posedge clk) begin
        if (step_valid) begin
            hcs = 32'd0; acs = 32'd0; lcs = 32'd0; ccs = 32'd0;
            for (i = 0; i < N; i = i + 1) begin
                hv  = {{14{h[i*18+17]}}, h[i*18 +: 18]};
                hcs = hcs + (i + 1) * hv;
                acs = acs + (i + 1) * acc[i];
                ccs = ccs + (i + 1) * (cadd[i*TW +: TW] + 256 * crem[i*TW +: TW]);
            end
            for (i = 0; i < NCON; i = i + 1)
                lcs = lcs + (i + 1) * load[i*16 +: 16];
            if (sel_valid)
                $fwrite(fd_tr, "%0d %0d %0d %0d %0d %0d %0d %0d %0d %0d\n", step_idx, sel_idx, nacc, acs,
                        $signed(obj), hcs, eoff, temp, lcs, ccs);
            else
                $fwrite(fd_tr, "%0d -1 %0d %0d %0d %0d %0d %0d %0d %0d\n", step_idx, nacc, acs,
                        $signed(obj), hcs, eoff, temp, lcs, ccs);
            if (fd_act != 0) begin
                act_d0 = act_cnt[0*32 +: 32] - act_prev[0*32 +: 32];
                act_d1 = act_cnt[1*32 +: 32] - act_prev[1*32 +: 32];
                act_d2 = act_cnt[2*32 +: 32] - act_prev[2*32 +: 32];
                act_d3 = act_cnt[3*32 +: 32] - act_prev[3*32 +: 32];
                act_d4 = act_cnt[4*32 +: 32] - act_prev[4*32 +: 32];
                act_d5 = act_cnt[5*32 +: 32] - act_prev[5*32 +: 32];
                act_d6 = act_cnt[6*32 +: 32] - act_prev[6*32 +: 32];
                act_d7 = act_cnt[7*32 +: 32] - act_prev[7*32 +: 32];
                $fwrite(fd_act, "%0d %0d %0d %0d %0d %0d %0d %0d %0d %0d\n", step_idx,
                        (nsteps > 0) ? (cyc - last_cyc - rs_cycles) : (cps_expect + cim_cycles),
                        act_d0, act_d1, act_d2, act_d3, act_d4, act_d5, act_d6, act_d7);
                act_prev = act_cnt;
            end
            if (fd_rs != 0 && rs_cycles != 16'd0)
                $fwrite(fd_rs, "%0d %0d\n", step_idx, rs_cycles);          // cycles spent in S_RST by the restart of this step
            if (nsteps > 0 && cyc - last_cyc != cps_expect + rs_cycles + cim_cycles) begin
                cps_err = cps_err + 1;
                if (cps_err <= 5)
                    $display("TB_TOP cps error at step %0d: %0d cycles, expected %0d + %0d restart + %0d cim", step_idx,
                             cyc - last_cyc, cps_expect, rs_cycles, cim_cycles);
            end
            last_cyc = cyc;
            nsteps   = nsteps + 1;
        end
    end

    // ------------------------------------------------------------ load, run, report
    reg [8*512-1:0] cfg_name, tr_name, act_name, rs_name;
    reg [8*8-1:0]   tok;
    reg [31:0]      a, d, start_cyc, maxcyc;
    reg [63:0]      bits, care;
    integer         fd, code, row, seg, nw, nt;
    reg             fail;

    initial begin
        fail = 1'b0;
        nw = 0;
        nt = 0;
        if (!$value$plusargs("cfg=%s", cfg_name)) begin
            $display("TB_TOP_END fail no +cfg");
            $finish;
        end
        if (!$value$plusargs("trace=%s", tr_name)) begin
            $display("TB_TOP_END fail no +trace");
            $finish;
        end
        if (!$value$plusargs("maxcyc=%d", maxcyc))
            maxcyc = 32'd10000000;

        repeat (3) @(posedge clk);
        @(negedge clk) rst_n = 1'b1;

        fd = $fopen(cfg_name, "r");
        if (fd == 0) begin
            $display("TB_TOP_END fail cannot open cfg");
            $finish;
        end
        while (!$feof(fd)) begin
            code = $fscanf(fd, "%s", tok);
            if (code == 1) begin
                if (tok == "w") begin
                    code = $fscanf(fd, "%h %h", a, d);
                    @(negedge clk);
                    cfg_we = 1'b1; cfg_addr = a[23:0]; cfg_wdata = d;
                    @(negedge clk);
                    cfg_we = 1'b0;
                    nw = nw + 1;
                end else if (tok == "t") begin
                    code = $fscanf(fd, "%d %d %h %h", row, seg, bits, care);
                    @(negedge clk);
                    while (tw_busy) @(negedge clk);
                    tw_en = 1'b1; tw_row = row; tw_seg = seg; tw_bits = bits; tw_care = care;
                    @(negedge clk);
                    tw_en = 1'b0;
                    nt = nt + 1;
                end else begin
                    $display("TB_TOP_END fail bad token in cfg");
                    $finish;
                end
            end
        end
        $fclose(fd);

        fd_tr = $fopen(tr_name, "w");
        if ($value$plusargs("act=%s", act_name)) fd_act = $fopen(act_name, "w");
        if ($value$plusargs("rs=%s", rs_name)) fd_rs = $fopen(rs_name, "w");
        cps_expect = dut.mode_knap ? (6 + dut.SEL_LAT + 2 * SEARCH_LAT) : (3 + dut.SEL_LAT);
        @(negedge clk) start = 1'b1;
        @(negedge clk) start = 1'b0;
        start_cyc = cyc;
        while (!done && (cyc - start_cyc) < maxcyc) @(posedge clk);
        @(posedge clk);   // the last step_valid is written at this edge
        #1;
        if (!done) begin
            fail = 1'b1;
            $display("TB_TOP timeout after %0d cycles", cyc - start_cyc);
        end
        $fwrite(fd_tr, "final %0d %0d %h %h\n", $signed(best_obj), best_step, x, best_x);
        $fclose(fd_tr);
        if (fd_act != 0) $fclose(fd_act);
        if (fd_rs != 0) $fclose(fd_rs);
        $display("TB_TOP cfg_writes=%0d tcam_rows=%0d steps=%0d run_cycles=%0d cps=%0d cps_err=%0d ovf=%0d restarts=%0d",
                 nw, nt, nsteps, cyc - start_cyc, cps_expect, cps_err, ovf, n_restart);
        $display("TB_TOP_COUNTERS searches=%0d writes=%0d wdrop=%0d err=%0d rows_en=%0d cells=%0d",
                 tc_search, tc_write, tc_wdrop, tc_err, tc_rows_en, tc_cells);
        if (TCL != 0)
            $display("TB_TOP_TL search=%0d write=%0d hit=%0d block=%0d", tl_cnt[31:0], tl_cnt[63:32], tl_cnt[95:64],
                     tl_cnt[127:96]);
        if (cps_err != 0) fail = 1'b1;
        if (ovf) fail = 1'b1;
        if (fail)
            $display("TB_TOP_END fail");
        else
            $display("TB_TOP_END ok");
        $finish;
    end
endmodule
