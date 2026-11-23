// P3.11: random-vector equivalence of select_tree and syn_select_tree_lvl (plus all-zero / all-one / one-hot cases).
module tb_select_eq;
    parameter N = 64;
    parameter NV = 200000;
    localparam L = $clog2(N);
    reg  [N-1:0] acc; reg [15:0] r16;
    wire v0, v1, v2; wire [L-1:0] i0, i1, i2; wire [L:0] c0, c1, c2;
    select_tree         #(.N(N)) a (.acc(acc), .r16(r16), .valid(v0), .idx(i0), .count(c0));
    syn_select_tree_lvl #(.N(N)) b (.acc(acc), .r16(r16), .valid(v1), .idx(i1), .count(c1));
    syn_select_tree_part #(.N(N)) c (.acc(acc), .r16(r16), .valid(v2), .idx(i2), .count(c2));
    integer t, w, bad, nv;
    initial begin
        bad = 0; nv = 0;
        for (t = 0; t < NV; t = t + 1) begin
            for (w = 0; w < N; w = w + 32) acc[w +: 32] = $random;
            if (t % 4 == 1) acc = acc & {N/32{$random}};          // sparse
            if (t % 4 == 2) acc = acc & {N/32{$random}} & {N/32{$random}};
            if (t == 0) acc = 0;
            if (t == 1) acc = {N{1'b1}};
            if (t >= 2 && t < 2 + N) acc = {{N-1{1'b0}},1'b1} << (t-2);
            r16 = $random;
            #1;
            nv = nv + 1;
            if (v0 !== v1 || c0 !== c1 || (v0 && i0 !== i1) || v0 !== v2 || c0 !== c2 || (v0 && i0 !== i2)) begin
                bad = bad + 1;
                if (bad < 5) $display("MISMATCH acc=%h r=%h idx %d/%d cnt %d/%d", acc, r16, i0, i1, c0, c1);
            end
        end
        $display("N=%0d vectors=%0d mismatches=%0d", N, nv, bad);
        $finish;
    end
endmodule
