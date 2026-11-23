// splitmix64 generator, used once per run to fill the xoshiro128** states through the seeding shift chain.
// "init" sets x = seed. "out" is the next output, mix(x + gamma); "next" moves x to x + gamma.
// So the outputs after init are z_0 = mix(seed + gamma), z_1 = mix(seed + 2 gamma), ... (SPEC section 5.6).
module splitmix64 (
    input  wire        clk,
    input  wire        init,
    input  wire [63:0] seed,
    input  wire        next,
    output wire [63:0] out
);
    reg [63:0] x;

    wire [63:0] xn = x + 64'h9E3779B97F4A7C15;
    wire [63:0] z1 = (xn ^ (xn >> 30)) * 64'hBF58476D1CE4E5B9;
    wire [63:0] z2 = (z1 ^ (z1 >> 27)) * 64'h94D049BB133111EB;
    assign out = z2 ^ (z2 >> 31);

    always @(posedge clk) begin
        if (init)
            x <= seed;
        else if (next)
            x <= xn;
    end
endmodule
