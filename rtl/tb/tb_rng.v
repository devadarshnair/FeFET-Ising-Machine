// Unit test: splitmix64 and xoshiro128** against golden vectors, and the seeding shift-chain order.
// Plusarg +vec=<file> (written by scripts/golden/gen_tests.py):
//   line 1: seed; lines 2-11: the first 10 splitmix64 outputs;
//   then for each of 5 generators (4 lanes + selection): "s0 s1 s2 s3" (chain-seeded state), then 64 outputs.
module tb_rng;
    localparam NG = 5;   // generators in the test chain (N = 4 lanes + 1)

    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg         sm_init = 1'b0, sm_next = 1'b0;
    reg  [63:0] seed;
    wire [63:0] sm_out;
    splitmix64 u_sm (.clk(clk), .init(sm_init), .seed(seed), .next(sm_next), .out(sm_out));

    // a chain of NG generators wired exactly as in tim_top
    reg               ld = 1'b0, adv = 1'b0;
    wire [128*NG-1:0] st;
    wire [32*NG-1:0]  out;
    genvar g;
    generate
        for (g = 0; g < NG; g = g + 1) begin : gen
            wire [63:0] next_low;
            if (g == NG - 1) begin : top_end
                assign next_low = sm_out;
            end else begin : link
                assign next_low = st[(g+1)*128 +: 64];
            end
            xoshiro128ss u_x (.clk(clk), .ld(ld), .ld_state({next_low, st[g*128+64 +: 64]}), .adv(adv),
                              .out(out[g*32 +: 32]), .state(st[g*128 +: 128]));
        end
    endgenerate

    reg [8*512-1:0] vec_name;
    reg [63:0]      want64;
    reg [31:0]      w0, w1, w2, w3, want32;
    integer         fd, code, k, gi, errors;
    reg [31:0]      outs [0:NG*64-1];
    reg [127:0]     states [0:NG-1];

    initial begin
        errors = 0;
        if (!$value$plusargs("vec=%s", vec_name)) begin
            $display("FAIL tb_rng: no +vec");
            $finish;
        end
        fd = $fopen(vec_name, "r");
        code = $fscanf(fd, "%h", seed);
        // splitmix64: out is the next output; next moves on
        @(negedge clk) sm_init = 1'b1;
        @(negedge clk) sm_init = 1'b0;
        for (k = 0; k < 10; k = k + 1) begin
            code = $fscanf(fd, "%h", want64);
            if (sm_out !== want64) begin
                errors = errors + 1;
                $display("tb_rng: splitmix64 output %0d = %h, want %h", k, sm_out, want64);
            end
            sm_next = 1'b1;
            @(negedge clk) sm_next = 1'b0;
        end
        for (gi = 0; gi < NG; gi = gi + 1) begin
            code = $fscanf(fd, "%h %h %h %h", w0, w1, w2, w3);
            states[gi] = {w3, w2, w1, w0};
            for (k = 0; k < 64; k = k + 1) begin
                code = $fscanf(fd, "%h", want32);
                outs[gi*64 + k] = want32;
            end
        end
        $fclose(fd);

        // seed the chain: init splitmix, then 2*NG shift cycles
        @(negedge clk) sm_init = 1'b1;
        @(negedge clk) begin sm_init = 1'b0; ld = 1'b1; sm_next = 1'b1; end
        repeat (2 * NG - 1) @(negedge clk);
        @(negedge clk) begin ld = 1'b0; sm_next = 1'b0; end
        for (gi = 0; gi < NG; gi = gi + 1)
            if (st[gi*128 +: 128] !== states[gi]) begin
                errors = errors + 1;
                $display("tb_rng: chain state %0d = %h, want %h", gi, st[gi*128 +: 128], states[gi]);
            end
        // 64 outputs of every generator
        for (k = 0; k < 64; k = k + 1) begin
            for (gi = 0; gi < NG; gi = gi + 1)
                if (out[gi*32 +: 32] !== outs[gi*64 + k]) begin
                    errors = errors + 1;
                    if (errors < 10)
                        $display("tb_rng: gen %0d output %0d = %h, want %h", gi, k, out[gi*32 +: 32],
                                 outs[gi*64 + k]);
                end
            adv = 1'b1;
            @(negedge clk) adv = 1'b0;
        end
        if (errors == 0)
            $display("PASS tb_rng (10 splitmix64 outputs, %0d chain states, %0d xoshiro128** outputs)", NG,
                     NG * 64);
        else
            $display("FAIL tb_rng: %0d mismatches", errors);
        $finish;
    end
endmodule
