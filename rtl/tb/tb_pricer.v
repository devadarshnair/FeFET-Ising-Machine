// Unit test: the TCAM pricer path (query_enc + tcam_stub + seg_adder) at NCON = 8 for Q = 8 (one segment) and
// Q = 16 (two segments). Rows hold the thermometer code of Wq = floor(Q*w/wmax); random loads and capacities give
// the slacks. The ADD and REM counts must equal the D5c hinge formula, computed here with integer division:
//   add_i = sum_j max(0, Wq_ij - floor(Q*max(s_j,0)/wmax))     for x_i = 0, else 0
//   rem_i = sum_j min(Wq_ij, floor(Q*max(-s_j,0)/wmax))         for x_i = 1, else 0
module tb_pricer;
    localparam NROW = 16, NCON = 8, LDW = 16;

    reg clk = 1'b0;
    always #5 clk = ~clk;
    reg rst_n = 1'b0;

    integer errors = 0, checks = 0;

    reg  [NCON*(LDW+1)-1:0] slack;
    reg  [5:0]              wmax;
    reg  [NROW-1:0]         x;
    reg                     ld = 1'b0, s_valid = 1'b0, s_rem = 1'b0;
    reg                     wr_en = 1'b0;
    reg  [3:0]              wr_row = 4'd0;
    reg                     wr_seg = 1'b0;
    reg  [63:0]             wr_bits = 64'd0;

    // ---- Q = 8: 64 cells, one segment
    wire [63:0]        am8, rm8;
    wire               busy8, done8;
    wire [NROW*7-1:0]  cnt8, tot8;
    query_enc #(.NCON(NCON), .NLEV(8), .SEGW(64), .NSEG(1), .LDW(LDW)) qe8 (
        .clk(clk), .ld(ld), .slack(slack), .wmax(wmax), .add_mask(am8), .rem_mask(rm8));
    tcam_stub #(.NROW(NROW), .SEGW(64), .NSEG(1), .CW(7), .SEARCH_LAT(2)) tc8 (
        .clk(clk), .rst_n(rst_n), .wr_en(wr_en), .wr_row(wr_row), .wr_seg(1'b0), .wr_bits(wr_bits),
        .wr_care({64{1'b1}}), .wr_busy(busy8), .s_valid(s_valid), .s_key(64'd0), .s_mask(s_rem ? rm8 : am8),
        .s_row_en(s_rem ? x : ~x), .s_done(done8), .r_cnt(cnt8), .err_en(1'b0), .err_thr(16'd0),
        .n_search(), .n_write(), .n_wdrop(), .n_err(), .n_rows_en(), .n_cells());
    seg_adder #(.NROW(NROW), .NSEG(1), .CW(7), .TW(7)) sa8 (.r_cnt(cnt8), .tot(tot8));

    // ---- Q = 16: 128 cells, two segments
    wire [127:0]       am16, rm16;
    wire               busy16, done16;
    wire [NROW*2*7-1:0] cnt16;
    wire [NROW*8-1:0]  tot16;
    reg                wr16 = 1'b0;
    query_enc #(.NCON(NCON), .NLEV(16), .SEGW(64), .NSEG(2), .LDW(LDW)) qe16 (
        .clk(clk), .ld(ld), .slack(slack), .wmax(wmax), .add_mask(am16), .rem_mask(rm16));
    tcam_stub #(.NROW(NROW), .SEGW(64), .NSEG(2), .CW(7), .SEARCH_LAT(2)) tc16 (
        .clk(clk), .rst_n(rst_n), .wr_en(wr16), .wr_row(wr_row), .wr_seg(wr_seg), .wr_bits(wr_bits),
        .wr_care({64{1'b1}}), .wr_busy(busy16), .s_valid(s_valid), .s_key(128'd0), .s_mask(s_rem ? rm16 : am16),
        .s_row_en(s_rem ? x : ~x), .s_done(done16), .r_cnt(cnt16), .err_en(1'b0), .err_thr(16'd0),
        .n_search(), .n_write(), .n_wdrop(), .n_err(), .n_rows_en(), .n_cells());
    seg_adder #(.NROW(NROW), .NSEG(2), .CW(7), .TW(8)) sa16 (.r_cnt(cnt16), .tot(tot16));

    integer w [0:NCON-1][0:NROW-1];
    integer s [0:NCON-1];
    integer seed, inst, trial, i, j, k, q, wq, fl, fv, want, got, ncase;
    reg [127:0] row;

    function integer imax(input integer a, input integer b); imax = (a > b) ? a : b; endfunction
    function integer imin(input integer a, input integer b); imin = (a < b) ? a : b; endfunction

    task write_rows(input integer qq);
        integer ii, jj, kk, ww;
        begin
            for (ii = 0; ii < NROW; ii = ii + 1) begin
                row = 128'd0;
                for (jj = 0; jj < NCON; jj = jj + 1) begin
                    ww = (qq * w[jj][ii]) / wmax;
                    for (kk = 1; kk <= qq; kk = kk + 1)
                        if (ww >= kk) row[jj*qq + kk - 1] = 1'b1;
                end
                if (qq == 8) begin
                    @(negedge clk); while (busy8) @(negedge clk);
                    wr_en = 1'b1; wr_row = ii; wr_bits = row[63:0];
                    @(negedge clk) wr_en = 1'b0;
                end else begin
                    @(negedge clk); while (busy16) @(negedge clk);
                    wr16 = 1'b1; wr_row = ii; wr_seg = 1'b0; wr_bits = row[63:0];
                    @(negedge clk); while (busy16) @(negedge clk);
                    wr16 = 1'b1; wr_seg = 1'b1; wr_bits = row[127:64];
                    @(negedge clk) wr16 = 1'b0;
                end
            end
        end
    endtask

    task search_and_check(input integer rem);
        integer ii, jj;
        begin
            @(negedge clk) begin s_valid = 1'b1; s_rem = rem; end
            @(negedge clk) s_valid = 1'b0;
            while (!(done8 && done16)) @(negedge clk);
            for (ii = 0; ii < NROW; ii = ii + 1) begin
                for (q = 8; q <= 16; q = q + 8) begin
                    want = 0;
                    if (x[ii] == rem) begin
                        for (jj = 0; jj < NCON; jj = jj + 1) begin
                            wq = (q * w[jj][ii]) / wmax;
                            fl = (q * imax(s[jj], 0)) / wmax;
                            fv = (q * imax(-s[jj], 0)) / wmax;
                            want = want + (rem ? imin(wq, fv) : imax(0, wq - fl));
                        end
                    end
                    got = (q == 8) ? tot8[ii*7 +: 7] : tot16[ii*8 +: 8];
                    checks = checks + 1;
                    if (got != want) begin
                        errors = errors + 1;
                        if (errors < 10)
                            $display("tb_pricer: Q=%0d row %0d %s count %0d want %0d", q, ii, rem ? "REM" : "ADD", got,
                                     want);
                    end
                end
            end
        end
    endtask

    initial begin
        seed = 4242; ncase = 0;
        repeat (2) @(negedge clk);
        rst_n = 1'b1;
        for (inst = 0; inst < 6; inst = inst + 1) begin
            wmax = (inst == 0) ? 6'd50 : 6'd30 + ({$random(seed)} % 34);
            for (j = 0; j < NCON; j = j + 1)
                for (i = 0; i < NROW; i = i + 1)
                    w[j][i] = 1 + {$random(seed)} % wmax;
            write_rows(8);
            write_rows(16);
            for (trial = 0; trial < 60; trial = trial + 1) begin
                for (j = 0; j < NCON; j = j + 1) begin
                    // slack around zero most of the time (where the hinge acts), sometimes large
                    s[j] = (trial % 5 == 0) ? ($random(seed) % 30000) : ($random(seed) % 200);
                    slack[j*(LDW+1) +: (LDW+1)] = s[j];
                end
                x = $random(seed);
                @(negedge clk) ld = 1'b1;
                @(negedge clk) ld = 1'b0;
                search_and_check(0);
                search_and_check(1);
                ncase = ncase + 1;
            end
        end
        if (errors == 0)
            $display("PASS tb_pricer (%0d slack cases, %0d row counts at Q = 8 and 16 equal the hinge formula)", ncase,
                     checks);
        else
            $display("FAIL tb_pricer: %0d of %0d counts wrong", errors, checks);
        $finish;
    end
endmodule
