// Unit test: I3 penalty ramp lam_t = lam_lo + floor((lam - lam_lo) * min(t, ramp) / ramp) (t = 1, 2, ...) against a
// 64-bit integer reference, for many (lam_lo, lam, ramp), including ramp = 1, D = 0, D < ramp and D >> ramp.
module tb_lam_ramp;
    reg         clk = 1'b0;
    always #5 clk = ~clk;
    reg         init = 1'b0, step = 1'b0;
    reg  [15:0] lo, dq;
    reg  [31:0] ramp, dr;
    wire [15:0] lam_t;
    lam_ramp dut (.clk(clk), .init(init), .step(step), .lam_lo(lo), .ramp(ramp), .dq(dq), .dr(dr), .lam_t(lam_t));

    integer errors = 0, checks = 0, seed = 4242, k, t, hold_chk;
    reg [63:0] d, want;
    reg [15:0] lam;

    task run_case(input [15:0] lo_i, input [15:0] lam_i, input [31:0] ramp_i);
        begin
            lo = lo_i; ramp = ramp_i; d = lam_i - lo_i;
            dq = d / ramp_i; dr = d % ramp_i;
            @(negedge clk) init = 1'b1;
            @(negedge clk) init = 1'b0;
            for (t = 1; t <= ramp_i + 3 && t <= 400; t = t + 1) begin
                want = lo_i + (d * ((t < ramp_i) ? t : ramp_i)) / ramp_i;
                checks = checks + 1;
                if (lam_t !== want[15:0]) begin
                    errors = errors + 1;
                    if (errors < 10) $display("tb_lam_ramp: lo=%0d lam=%0d ramp=%0d t=%0d: %0d want %0d", lo_i, lam_i, ramp_i, t, lam_t, want[15:0]);
                end
                if (t == 2) begin          // no step pulse: holds
                    @(negedge clk); @(negedge clk);
                    if (lam_t !== lo_i + (d * ((2 < ramp_i) ? 2 : ramp_i)) / ramp_i) begin errors = errors + 1; $display("tb_lam_ramp: moved without a step"); end
                end
                @(negedge clk) step = 1'b1;
                @(negedge clk) step = 1'b0;
            end
        end
    endtask

    initial begin
        run_case(16'd0, 16'd10, 32'd4);
        run_case(16'd2, 16'd10, 32'd4);         // the golden test_i3 hand-computed ramp: 4 6 8 10 10 10
        run_case(16'd7, 16'd7, 32'd5);          // D = 0
        run_case(16'd0, 16'd3, 32'd1);          // ramp 1: lam from the first step
        run_case(16'd5, 16'd9, 32'd100);        // D < ramp
        run_case(16'd0, 16'hFFFF, 32'd7);
        for (k = 0; k < 400; k = k + 1) begin
            lam = $random(seed);
            run_case(($random(seed) & 16'h3FFF) % (lam + 1), lam, 1 + ({$random(seed)} % ((k % 3 == 0) ? 3000 : 60)));
        end
        if (errors == 0) $display("PASS tb_lam_ramp (%0d checks)", checks);
        else             $display("FAIL tb_lam_ramp: %0d of %0d checks wrong", errors, checks);
        $finish;
    end
endmodule
