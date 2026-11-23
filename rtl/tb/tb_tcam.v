// Unit test: the stand-in TCAM (tcam_stub) at NROW = 16, NSEG = 2, for SEARCH_LAT = 3 and SEARCH_LAT = 1.
// Checks against a shadow copy in the testbench:
//   counts = popcount((bits ^ key) & care & mask) per enabled row and segment, 0 for disabled rows;
//   s_done exactly SEARCH_LAT cycles after s_valid, r_cnt unchanged before s_done;
//   write busy time, dropped writes leave storage unchanged, event counters;
//   error hook: with err_en = 1 the counts differ from exact by at most 1, stay in 0..64, and n_err counts them.
module tb_tcam;
    localparam NROW = 16, SEGW = 64, NSEG = 2, CW = 7, KW = NSEG * SEGW;

    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg              rst_n = 1'b0;
    reg              wr_en = 1'b0;
    reg [3:0]        wr_row = 4'd0;
    reg              wr_seg = 1'b0;
    reg [SEGW-1:0]   wr_bits = 0, wr_care = 0;
    reg              s_valid = 1'b0;
    reg [KW-1:0]     s_key = 0, s_mask = 0;
    reg [NROW-1:0]   s_row_en = 0;
    reg              err_en = 1'b0;
    reg [15:0]       err_thr = 16'd0;

    wire                    busy3, busy1, done3, done1;
    wire [NROW*NSEG*CW-1:0] cnt3, cnt1;
    wire [31:0]             ns3, nw3, nd3, ne3, ns1, nw1, nd1, ne1;
    wire [47:0]             nr3, nc3, nr1, nc1;

    tcam_stub #(.NROW(NROW), .SEGW(SEGW), .NSEG(NSEG), .CW(CW), .SEARCH_LAT(3), .WRITE_LAT(4)) u3 (
        .clk(clk), .rst_n(rst_n), .wr_en(wr_en), .wr_row(wr_row), .wr_seg(wr_seg), .wr_bits(wr_bits),
        .wr_care(wr_care), .wr_busy(busy3), .s_valid(s_valid), .s_key(s_key), .s_mask(s_mask),
        .s_row_en(s_row_en), .s_done(done3), .r_cnt(cnt3), .err_en(err_en), .err_thr(err_thr),
        .n_search(ns3), .n_write(nw3), .n_wdrop(nd3), .n_err(ne3), .n_rows_en(nr3), .n_cells(nc3));
    tcam_stub #(.NROW(NROW), .SEGW(SEGW), .NSEG(NSEG), .CW(CW), .SEARCH_LAT(1), .WRITE_LAT(4)) u1 (
        .clk(clk), .rst_n(rst_n), .wr_en(wr_en), .wr_row(wr_row), .wr_seg(wr_seg), .wr_bits(wr_bits),
        .wr_care(wr_care), .wr_busy(busy1), .s_valid(s_valid), .s_key(s_key), .s_mask(s_mask),
        .s_row_en(s_row_en), .s_done(done1), .r_cnt(cnt1), .err_en(1'b0), .err_thr(16'd0),
        .n_search(ns1), .n_write(nw1), .n_wdrop(nd1), .n_err(ne1), .n_rows_en(nr1), .n_cells(nc1));

    reg [SEGW-1:0] sb [0:NROW*NSEG-1];
    reg [SEGW-1:0] sc [0:NROW*NSEG-1];
    integer seed, r, g, t, k, errors, n_search, rows_en, cells, n_drop, lat3, lat1, n_changed;
    reg [NROW*NSEG*CW-1:0] before3, want;

    function integer popc;
        input [KW-1:0] v;
        integer b;
        begin
            popc = 0;
            for (b = 0; b < KW; b = b + 1) popc = popc + v[b];
        end
    endfunction

    task do_write(input integer row, input integer seg, input [SEGW-1:0] b, input [SEGW-1:0] c);
        begin
            @(negedge clk);
            while (busy3 || busy1) @(negedge clk);
            wr_en = 1'b1; wr_row = row; wr_seg = seg; wr_bits = b; wr_care = c;
            @(negedge clk) wr_en = 1'b0;
            sb[row*NSEG+seg] = b;
            sc[row*NSEG+seg] = c;
        end
    endtask

    task make_want;
        integer rr, gg;
        begin
            for (rr = 0; rr < NROW; rr = rr + 1)
                for (gg = 0; gg < NSEG; gg = gg + 1)
                    want[(rr*NSEG+gg)*CW +: CW] = s_row_en[rr] ?
                        popc({{(KW-SEGW){1'b0}}, (sb[rr*NSEG+gg] ^ s_key[gg*SEGW +: SEGW]) & sc[rr*NSEG+gg] &
                              s_mask[gg*SEGW +: SEGW]}) : 0;
        end
    endtask

    // one search on both instances; measures the latency of each and checks r_cnt stays put before s_done
    task do_search;
        begin
            @(negedge clk);
            s_key = {$random(seed), $random(seed), $random(seed), $random(seed)};
            s_mask = {$random(seed), $random(seed), $random(seed), $random(seed)};
            s_row_en = $random(seed);
            before3 = cnt3;
            s_valid = 1'b1;
            make_want;
            n_search = n_search + 1;
            rows_en = rows_en + popc({{(KW-NROW){1'b0}}, s_row_en});
            cells = cells + popc({{(KW-NROW){1'b0}}, s_row_en}) * popc(s_mask);
            lat3 = -1; lat1 = -1;
            for (k = 1; k <= 5; k = k + 1) begin
                @(negedge clk) s_valid = 1'b0;
                if (done3 && lat3 < 0) lat3 = k;
                if (done1 && lat1 < 0) lat1 = k;
                if (lat3 < 0 && cnt3 !== before3) begin
                    errors = errors + 1;
                    $display("tb_tcam: r_cnt changed before s_done");
                end
            end
            if (lat3 != 3 || lat1 != 1) begin
                errors = errors + 1;
                if (errors < 10) $display("tb_tcam: latency %0d and %0d, want 3 and 1", lat3, lat1);
            end
        end
    endtask

    initial begin
        errors = 0; seed = 2026; n_search = 0; rows_en = 0; cells = 0; n_drop = 0; n_changed = 0;
        repeat (2) @(negedge clk);
        rst_n = 1'b1;
        for (r = 0; r < NROW; r = r + 1)
            for (g = 0; g < NSEG; g = g + 1)
                do_write(r, g, {$random(seed), $random(seed)}, (r % 3 == 0) ? {SEGW{1'b1}} :
                         {$random(seed), $random(seed)});
        // a write while busy is dropped
        @(negedge clk);
        while (busy3 || busy1) @(negedge clk);
        wr_en = 1'b1; wr_row = 0; wr_seg = 0; wr_bits = 0; wr_care = {SEGW{1'b1}};
        @(negedge clk) begin wr_bits = {SEGW{1'b1}}; end    // second cycle: busy, dropped
        @(negedge clk) wr_en = 1'b0;
        sb[0] = 0; sc[0] = {SEGW{1'b1}};
        n_drop = 1;
        repeat (6) @(negedge clk);
        if (!busy3 && nd3 != n_drop) begin errors = errors + 1; $display("tb_tcam: n_wdrop %0d", nd3); end
        for (t = 0; t < 400; t = t + 1) begin
            do_search;
            if (cnt3 !== want || cnt1 !== want) begin
                errors = errors + 1;
                if (errors < 10) $display("tb_tcam: search %0d counts differ from reference", t);
            end
            if (t % 50 == 0)
                do_write({$random(seed)} % NROW, {$random(seed)} % NSEG, {$random(seed), $random(seed)},
                         {$random(seed), $random(seed)});
        end
        if (ns3 != n_search || ns1 != n_search || nr3 != rows_en || nc3 != cells || nw3 != NROW * NSEG + 1 + 8 ||
            nd3 != n_drop) begin
            errors = errors + 1;
            $display("tb_tcam: counters searches %0d/%0d rows %0d/%0d cells %0d/%0d writes %0d drops %0d", ns3,
                     n_search, nr3, rows_en, nc3, cells, nw3, nd3);
        end
        // error hook: about half of the counts are pushed by +-1 on the SEARCH_LAT = 3 instance
        err_en = 1'b1; err_thr = 16'h8000;
        for (t = 0; t < 100; t = t + 1) begin
            do_search;
            for (k = 0; k < NROW * NSEG; k = k + 1) begin
                if (cnt3[k*CW +: CW] != want[k*CW +: CW]) n_changed = n_changed + 1;
                if (cnt3[k*CW +: CW] > 64 || (cnt3[k*CW +: CW] + 1 < want[k*CW +: CW]) ||
                    (cnt3[k*CW +: CW] > want[k*CW +: CW] + 1)) begin
                    errors = errors + 1;
                    if (errors < 10) $display("tb_tcam: injected error too large");
                end
            end
            if (cnt1 !== want) begin errors = errors + 1; $display("tb_tcam: error hook leaked into err_en = 0"); end
        end
        if (ne3 != n_changed || n_changed < 200) begin
            errors = errors + 1;
            $display("tb_tcam: n_err %0d, changed counts %0d", ne3, n_changed);
        end
        if (errors == 0)
            $display("PASS tb_tcam (%0d searches at latency 3 and 1, %0d writes, %0d injected count errors)",
                     n_search, nw3, n_changed);
        else
            $display("FAIL tb_tcam: %0d errors", errors);
        $finish;
    end
endmodule
