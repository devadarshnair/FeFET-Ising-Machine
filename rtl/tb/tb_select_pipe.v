// Unit test: select_tree_pipe equals select_tree (the single-cycle reference) for every held (acc, r16), for several
// pipeline cut masks at N = 16, 64 and 256: only the forced multiply register (latency 2), cuts on every adder level
// and every walk step (maximum latency), and mixed masks. Inputs are held for LAT cycles, then outputs are compared
// to the combinational tree at the same inputs. Pattern mix: random, sparse, dense, empty, full, single bit.
module tb_select_pipe;
    reg         clk = 1'b0;
    always #5 clk = ~clk;
    reg  [255:0] acc;
    reg  [15:0]  r16;
    integer errors = 0, checks = 0;
    reg chk_en = 1'b0;
    integer cyc_in_pat = 0;
    always @(posedge clk) cyc_in_pat <= cyc_in_pat + 1;     // posedges since the pattern was applied minus one (set by the driver)

    // one checker cell: a pipelined tree and the reference at the same N, comparison after LAT cycles of held inputs
    // expected latency = 2 + popcount(ADD_CUT) + popcount(WALK_CUT)
    wire [15:0] errs;
    genvar k;
    generate
        for (k = 0; k < 9; k = k + 1) begin : cells
            localparam N = (k < 3) ? 16 : (k < 6) ? 64 : 256;
            localparam L = $clog2(N);
            localparam [31:0] AC = (k % 3 == 0) ? 32'd0 : (k % 3 == 1) ? ((32'd1 << L) - 1) : 32'b10101010;
            localparam [31:0] WC = (k % 3 == 0) ? 32'd0 : (k % 3 == 1) ? ((32'd1 << (L - 1)) - 1) : 32'b01010101;
            localparam [31:0] ACM = AC & ((32'd1 << L) - 1);
            localparam [31:0] WCM = WC & ((32'd1 << (L - 1)) - 1);
            function integer pc;
                input [31:0] v;
                integer b;
                begin pc = 0; for (b = 0; b < 32; b = b + 1) pc = pc + v[b]; end
            endfunction
            localparam LAT = 2 + pc(ACM) + pc(WCM);
            wire         vp, vr;
            wire [L-1:0] ip, ir;
            wire [L:0]   cp, cr;
            select_tree_pipe #(.N(N), .ADD_CUT(AC), .WALK_CUT(WC)) dut (.clk(clk), .acc(acc[N-1:0]), .r16(r16), .valid(vp), .idx(ip), .count(cp));
            select_tree      #(.N(N))                               refm (.acc(acc[N-1:0]), .r16(r16), .valid(vr), .idx(ir), .count(cr));
            reg bad = 1'b0;
            always @(negedge clk) if (chk_en && cyc_in_pat == LAT - 2) begin
                if (vp !== vr || ip !== ir || cp !== cr) begin
                    bad = 1'b1;
                    if (errors < 8) $display("tb_select_pipe: cell %0d N=%0d AC=%b WC=%b LAT=%0d acc=%h r16=%h got v%b i%0d c%0d want v%b i%0d c%0d",
                                             k, N, AC, WC, LAT, acc[N-1:0], r16, vp, ip, cp, vr, ir, cr);
                    errors = errors + 1;
                end
                checks = checks + 1;
            end
        end
    endgenerate

    integer p, i, seed;
    reg [255:0] pat;
    task apply;
        input [255:0] a;
        input [15:0]  r;
        begin
            @(negedge clk);
            acc = a; r16 = r; cyc_in_pat = -1; chk_en = 1'b1;     // first posedge after this makes cyc_in_pat 0; the checker fires after LAT-1 edges
            repeat (20) @(negedge clk);
            chk_en = 1'b0;
        end
    endtask
    initial begin
        seed = 20260;
        acc = 256'd0; r16 = 16'd0;
        apply(256'd0, 16'h1234);
        apply({256{1'b1}}, 16'hFFFF);
        apply({256{1'b1}}, 16'h0000);
        apply(256'd1, 16'h8000);
        apply(256'd1 << 255, 16'hFFFF);
        apply(256'd1 << 15, 16'h7000);
        for (p = 0; p < 160; p = p + 1) begin
            pat = 256'd0;
            for (i = 0; i < 8; i = i + 1) pat = {pat[223:0], $random(seed)};
            case (p % 4)
                0: ;                                   // dense random
                1: pat = pat & {8{$random(seed)}} & {8{$random(seed)}};   // sparse
                2: pat = pat | {8{$random(seed)}} | {8{$random(seed)}};   // very dense
                3: pat = pat & ~(pat << 3) & ~(pat >> 7);                 // clumped
            endcase
            apply(pat, $random(seed));
        end
        if (errors == 0 && checks == 9 * 166) $display("PASS tb_select_pipe %0d checks, 9 cut configurations at N = 16/64/256", checks);
        else $display("FAIL tb_select_pipe %0d errors in %0d checks", errors, checks);
        $finish;
    end
endmodule
