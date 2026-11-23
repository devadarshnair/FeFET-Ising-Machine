// Unit test: count-tree selection. For N = 16 and N = 64, fixed and random accept patterns are checked against a
// behavioural reference (r = (r16 * c) >> 16, then the r-th set bit counting from lane 0). For the fixed patterns
// every one of the 2^16 values of r16 is tried, so the pick distribution is checked exactly, not statistically.
module tb_select;
    reg  [15:0] r16;
    reg  [15:0] acc16;
    reg  [63:0] acc64;
    wire        v16, v64;
    wire [3:0]  i16;
    wire [5:0]  i64;
    wire [4:0]  c16;
    wire [6:0]  c64;

    select_tree #(.N(16)) u16 (.acc(acc16), .r16(r16), .valid(v16), .idx(i16), .count(c16));
    select_tree #(.N(64)) u64 (.acc(acc64), .r16(r16), .valid(v64), .idx(i64), .count(c64));

    integer errors, checks, seed, p, v, n_set;

    // reference: index of the r-th set bit of a (width w), or -1
    function integer ref_pick;
        input [63:0] a;
        input integer w;
        input [15:0] rv;
        integer c, r, b, seen;
        begin
            c = 0;
            for (b = 0; b < w; b = b + 1) c = c + a[b];
            ref_pick = -1;
            if (c > 0) begin
                r = (rv * c) >> 16;
                seen = 0;
                for (b = 0; b < w; b = b + 1)
                    if (a[b]) begin
                        if (seen == r && ref_pick < 0) ref_pick = b;
                        seen = seen + 1;
                    end
            end
        end
    endfunction

    function integer popc;
        input [63:0] a;
        input integer w;
        integer b;
        begin
            popc = 0;
            for (b = 0; b < w; b = b + 1) popc = popc + a[b];
        end
    endfunction

    task check16;
        integer want;
        begin
            #1;
            want = ref_pick({48'd0, acc16}, 16, r16);
            checks = checks + 1;
            if (c16 != popc({48'd0, acc16}, 16) || v16 != (acc16 != 0) || (want >= 0 && i16 != want)) begin
                errors = errors + 1;
                if (errors < 10)
                    $display("tb_select: N=16 acc=%h r16=%h got idx %0d count %0d, want %0d", acc16, r16, i16, c16,
                             want);
            end
        end
    endtask

    task check64;
        integer want;
        begin
            #1;
            want = ref_pick(acc64, 64, r16);
            checks = checks + 1;
            if (c64 != popc(acc64, 64) || v64 != (acc64 != 0) || (want >= 0 && i64 != want)) begin
                errors = errors + 1;
                if (errors < 10)
                    $display("tb_select: N=64 acc=%h r16=%h got idx %0d count %0d, want %0d", acc64, r16, i64, c64,
                             want);
            end
        end
    endtask

    initial begin
        errors = 0;
        checks = 0;
        seed = 12345;
        // fixed patterns, exhaustive over r16
        for (p = 0; p < 6; p = p + 1) begin
            case (p)
                0: begin acc16 = 16'h0001; acc64 = 64'h8000000000000000; end
                1: begin acc16 = 16'h8001; acc64 = 64'h0000000100000001; end
                2: begin acc16 = 16'h00F7; acc64 = 64'hF000000000000007; end   // clustered bits (DA tree bias case)
                3: begin acc16 = 16'hFFFF; acc64 = 64'hFFFFFFFFFFFFFFFF; end
                4: begin acc16 = 16'hA5A5; acc64 = 64'h0123456789ABCDEF; end
                default: begin acc16 = 16'h0000; acc64 = 64'h0; end
            endcase
            for (v = 0; v < 65536; v = v + 1) begin
                r16 = v;
                check16;
                check64;
            end
        end
        // random patterns, random r16
        for (p = 0; p < 3000; p = p + 1) begin
            acc16 = $random(seed);
            acc64 = {$random(seed), $random(seed)};
            if (p % 3 == 0) acc64 = acc64 & {$random(seed), $random(seed)} & {$random(seed), $random(seed)};
            for (v = 0; v < 16; v = v + 1) begin
                r16 = $random(seed);
                check16;
                check64;
            end
        end
        if (errors == 0)
            $display("PASS tb_select (%0d checks, 6 patterns exhaustive over r16 at N=16 and N=64)", checks);
        else
            $display("FAIL tb_select: %0d of %0d checks wrong", errors, checks);
        $finish;
    end
endmodule
