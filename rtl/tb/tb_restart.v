// Unit test of restart_unit (N = 8): the stall counter (mesa and kc2 semantics, all improvement patterns), the mesa
// reload (all 65536 pairs of current and best state: the flipped spins are exactly the differing spins, ascending),
// and the kc2 kick (all 255 enable masks x all L, three restarts in a row on the persistent permutation, random draws,
// against a Fisher-Yates reference written in this file). Prints "PASS tb_restart <summary>" or "FAIL ...".
module tb_restart;
    parameter N = 8;
    localparam LOG2N = 3;

    reg clk = 1'b0;
    always #5 clk = ~clk;
    reg rst_n = 1'b0;

    reg  [1:0]         arm = 2'd0;
    reg  [31:0]        kcfg = 32'd1;
    reg  [15:0]        lcfg = 16'd10;
    reg                rsched = 1'b0;
    reg  [N-1:0]       lane_en = {N{1'b1}};
    reg                seed_init = 1'b0, pinit = 1'b0, init = 1'b0, upd = 1'b0, flipped_ok = 1'b0, imp_best = 1'b0;
    reg  signed [31:0] f_new = 32'sd0, f = 32'sd0;
    reg  [N-1:0]       x = {N{1'b0}}, best_x = {N{1'b0}};
    reg                feas_now = 1'b1;
    reg  [31:0]        lcg = 32'd12345;
    wire trig, rd, flip, gen_adv, sched_rst, kc2_fin, fin;
    wire [LOG2N-1:0] idx;
    wire [31:0] n_restart;

    restart_unit #(.N(N)) dut (
        .clk(clk), .rst_n(rst_n), .init(init), .arm(arm), .kcfg(kcfg), .lcfg(lcfg), .rsched(rsched),
        .lane_en(lane_en), .seed_init(seed_init), .pinit(pinit), .upd(upd), .flipped_ok(flipped_ok),
        .imp_best(imp_best), .f_new(f_new), .x(x), .best_x(best_x), .f(f), .feas_now(feas_now), .rng_o(lcg),
        .trig(trig), .rd(rd), .flip(flip), .idx(idx), .gen_adv(gen_adv), .sched_rst(sched_rst), .kc2_fin(kc2_fin),
        .fin(fin), .n_restart(n_restart)
    );

    integer errors = 0;
    integer nchk = 0;

    always @(posedge clk) begin
        if (gen_adv) lcg <= lcg * 32'd1664525 + 32'd1013904223;
        if (flip) x[idx] <= ~x[idx];
    end

    task fail(input [255:0] what);
        begin
            errors = errors + 1;
            if (errors < 10) $display("FAIL tb_restart %0s at %0t", what, $time);
        end
    endtask

    // one UPD cycle; returns trig seen in that cycle, then waits for the restart to finish
    reg        trig_seen;
    integer    wait_n;
    task do_upd;
        begin
            @(negedge clk);
            upd = 1'b1;
            #1 trig_seen = trig;
            @(negedge clk);
            upd = 1'b0; flipped_ok = 1'b0; imp_best = 1'b0;
            wait_n = 0;
            while (trig_seen && !fin && wait_n < 100) begin @(negedge clk); wait_n = wait_n + 1; end
            if (trig_seen) @(negedge clk);   // fin cycle passed
        end
    endtask

    // ---- reference state for part A
    integer stall_ref;
    integer epoch_ref;
    integer pat, step, kk, a_arm, ref_trig;
    integer i, j, mask, ll, rep, sz, ai, jj, tmp, flips_expected_n, flips_seen_n;
    reg [31:0] lcg_ref, drw;
    reg [LOG2N-1:0] pref [0:N-1];
    reg [LOG2N-1:0] exp_seq [0:N-1];
    reg [LOG2N-1:0] seen_seq [0:N-1];
    reg [N-1:0] xs, bs;
    integer sched_cnt;
    reg  [63:0] pr;

    always @(posedge clk) begin
        if (flip && flips_seen_n < N) begin seen_seq[flips_seen_n] <= idx; end
        if (flip) flips_seen_n <= flips_seen_n + 1;
        if (sched_rst) sched_cnt <= sched_cnt + 1;
    end

    initial begin
        flips_seen_n = 0; sched_cnt = 0;
        repeat (3) @(negedge clk);
        rst_n = 1'b1;
        @(negedge clk);

        // permutation initialisation with all lanes enabled (needed before part A is irrelevant: no restart acts on it)
        // ---------------------------------------------------------------- part A: stall counter and trigger
        for (a_arm = 2; a_arm <= 3; a_arm = a_arm + 1)
            for (kk = 1; kk <= 4; kk = kk + 1)
                for (pat = 0; pat < 256; pat = pat + 1) begin
                    arm = a_arm; kcfg = kk; lcfg = 16'd0;    // L = 0: kc2 restart is empty, keeps the test on the counter
                    @(negedge clk); init = 1'b1; @(negedge clk); init = 1'b0;
                    stall_ref = 0; epoch_ref = 0;
                    for (step = 0; step < 8; step = step + 1) begin
                        // improvement bit: mesa -> imp_best; kc2 -> f_new above the epoch best
                        flipped_ok = 1'b1;
                        imp_best   = pat[step];
                        f_new      = pat[step] ? epoch_ref + 1 : epoch_ref;
                        f          = f_new;
                        if (pat[step]) begin if (a_arm == 3) epoch_ref = epoch_ref + 1; stall_ref = 0; end
                        else stall_ref = stall_ref + 1;
                        ref_trig = (stall_ref >= kk);
                        do_upd;
                        nchk = nchk + 1;
                        if (trig_seen !== (ref_trig != 0)) fail("trigger timing");
                        if (ref_trig) begin
                            stall_ref = 0;
                            if (a_arm == 3) epoch_ref = f_new;   // kick of 0 spins: epoch best := f (feasible)
                        end
                    end
                end
        flipped_ok = 1'b0; imp_best = 1'b0;

        // ---------------------------------------------------------------- part B: mesa reload, all (x, best_x)
        arm = 2'd2; kcfg = 32'd1; rsched = 1'b0;
        for (i = 0; i < 256; i = i + 1)
            for (j = 0; j < 256; j = j + 1) begin
                @(negedge clk); init = 1'b1; @(negedge clk); init = 1'b0;
                x = i; best_x = j; flips_seen_n = 0; sched_cnt = 0;
                do_upd;
                nchk = nchk + 1;
                if (!trig_seen) fail("mesa no trigger");
                if (x !== j[N-1:0]) fail("mesa final state");
                xs = i ^ j; flips_expected_n = 0;
                for (ai = 0; ai < N; ai = ai + 1) if (xs[ai]) begin
                    if (seen_seq[flips_expected_n] !== ai) fail("mesa flip order");
                    flips_expected_n = flips_expected_n + 1;
                end
                if (flips_seen_n !== flips_expected_n) fail("mesa flip count");
                if (sched_cnt !== 1) fail("mesa schedule reset");
            end

        // ---------------------------------------------------------------- part C: kc2 kick, persistent permutation
        arm = 2'd3; kcfg = 32'd1; rsched = 1'b0; feas_now = 1'b1;
        for (mask = 1; mask < 256; mask = mask + 1)
            for (ll = 0; ll <= 8; ll = ll + 1) begin
                lane_en = mask; lcfg = ll;
                @(negedge clk); seed_init = 1'b1; @(negedge clk); seed_init = 1'b0;
                pinit = 1'b1; repeat (N + 2) @(negedge clk); pinit = 1'b0;
                @(negedge clk); init = 1'b1; @(negedge clk); init = 1'b0;
                sz = 0;
                for (i = 0; i < N; i = i + 1) if (mask[i]) begin pref[sz] = i; sz = sz + 1; end
                for (rep = 0; rep < 3; rep = rep + 1) begin
                    x = rep * 37; f = 0; f_new = 0; flipped_ok = 1'b0; imp_best = 1'b0;
                    xs = x;
                    lcg_ref = lcg;
                    flips_expected_n = (ll > sz - 1) ? sz - 1 : ll;
                    for (ai = 0; ai < flips_expected_n; ai = ai + 1) begin
                        pr = lcg_ref * (sz - ai);
                        jj = ai + pr[63:32];
                        tmp = pref[ai]; pref[ai] = pref[jj]; pref[jj] = tmp;
                        exp_seq[ai] = pref[ai];
                        lcg_ref = lcg_ref * 32'd1664525 + 32'd1013904223;
                    end
                    flips_seen_n = 0;
                    do_upd;      // f_new = f = 0 is not above the epoch best (0): no improvement, K = 1 triggers
                    nchk = nchk + 1;
                    if (!trig_seen) fail("kc2 no trigger");
                    if (flips_seen_n !== flips_expected_n) fail("kc2 flip count");
                    for (ai = 0; ai < flips_expected_n; ai = ai + 1) begin
                        xs[exp_seq[ai]] = ~xs[exp_seq[ai]];
                        if (seen_seq[ai] !== exp_seq[ai]) fail("kc2 kicked lane");
                        if (!mask[seen_seq[ai]]) fail("kc2 kicked a disabled lane");
                    end
                    if (x !== xs) fail("kc2 final state");
                    if (lcg !== lcg_ref) fail("kc2 draw count");
                    @(negedge clk);
                end
            end

        if (errors == 0) $display("PASS tb_restart %0d checks: stall counter (mesa, kc2), mesa reload 65536 pairs, kc2 kick 255 masks x 9 L x 3", nchk);
        else $display("FAIL tb_restart %0d errors", errors);
        $finish;
    end
endmodule
