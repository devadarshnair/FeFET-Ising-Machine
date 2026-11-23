// Unit test: acceptance unit against a 64-bit integer reference of SPEC 5.2, on random inputs and edge cases,
// with and without the I11 greedy mode (theta = E_off = 0).
module tb_accept;
    localparam HW = 18, TW = 7, LW = 12, EW = 24;

    reg  [HW-1:0] h;
    reg           x;
    reg  [TW-1:0] ca, cr;
    reg  [15:0]   lam;
    reg  [2:0]    gsh;
    reg  [EW-1:0] eoff;
    reg  [31:0]   temp;
    reg  [LW-1:0] lval;
    reg           greedy;
    wire [HW-1:0] gain;
    wire          acc;

    accept_unit #(.HW(HW), .TW(TW), .LW(LW), .EW(EW)) dut (
        .h(h), .h_acc(h), .x(x), .cnt_add(ca), .cnt_rem(cr), .lam(lam), .gsh(gsh), .eoff(eoff), .temp(temp), .lval(lval), .greedy(greedy),
        .gain(gain), .acc(acc)
    );

    integer errors, checks, seed, k, n_acc;
    reg signed [63:0] hv, g, geff, theta, sum;

    task check;
        begin
            #1;
            hv    = $signed(h);
            g     = x ? -hv : hv;
            geff  = g * (64'sd1 << gsh) - $signed({48'd0, lam}) * ca + $signed({48'd0, lam}) * cr;
            theta = ($signed({32'd0, temp}) * lval) >>> 24;
            sum   = greedy ? geff : geff + eoff + theta;
            checks = checks + 1;
            if (acc !== (sum >= 0) || $signed(gain) != g) begin
                errors = errors + 1;
                if (errors < 10)
                    $display("tb_accept: h=%0d x=%0d ca=%0d cr=%0d lam=%0d gsh=%0d eoff=%0d T=%0d L=%0d greedy=%0d: acc %b gain %0d, want %b %0d",
                             hv, x, ca, cr, lam, gsh, eoff, temp, lval, greedy, acc, $signed(gain), sum >= 0, g);
            end
            n_acc = n_acc + acc;
        end
    endtask

    initial begin
        errors = 0; checks = 0; seed = 777; n_acc = 0; greedy = 0;
        // edge cases: sum exactly 0 accepts, -1 rejects
        h = 0; x = 0; ca = 0; cr = 0; lam = 0; gsh = 0; eoff = 0; temp = 0; lval = 0; check;
        h = -1; check;
        h = 1; x = 1; check;
        temp = 32'h00010000; lval = 12'd256; h = -1; x = 0; check;          // theta = 1 exactly
        h = -2; check;
        // extremes
        h = 18'h1FFFF; x = 1; gsh = 4; ca = 0; cr = 7'd127; lam = 16'hFFFF; eoff = 24'hFFFFFF;
        temp = 32'hFFFFFFFF; lval = 12'hFFF; check;
        h = 18'h20001; x = 0; ca = 7'd127; cr = 0; eoff = 0; temp = 0; lval = 0; check;
        x = 1; check;
        greedy = 1; temp = 32'h00010000; lval = 12'd256; eoff = 24'd1000; h = -1; x = 0; check;   // greedy ignores theta and E_off: rejects
        h = 0; check;                                                                              // geff = 0 accepts
        greedy = 0;
        // random, with a mix of scales so both outcomes are common
        for (k = 0; k < 40000; k = k + 1) begin
            h    = $random(seed) % 30000;
            x    = $random(seed);
            gsh  = ($random(seed) & 7) % 5;
            lam  = (k % 4 == 0) ? 16'd0 : ($random(seed) & 16'h0FFF);
            ca   = $random(seed) % 65;
            cr   = $random(seed) % 65;
            eoff = (k % 3 == 0) ? 24'd0 : ($random(seed) & 24'h03FFFF);
            temp = $random(seed) & 32'h0FFFFFFF;
            lval = $random(seed);
            greedy = (k % 5 == 4);
            check;
        end
        if (errors == 0)
            $display("PASS tb_accept (%0d checks, %0d accepted)", checks, n_acc);
        else
            $display("FAIL tb_accept: %0d of %0d checks wrong", errors, checks);
        $finish;
    end
endmodule
