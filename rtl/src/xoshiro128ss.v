// xoshiro128** 1.1 random number generator (Blackman and Vigna), one per lane plus one for selection.
// The 32-bit output is a function of the current state. "adv" moves to the next state at the clock edge.
// "ld" loads a full state (used by the seeding shift chain) and has priority over "adv".
// State layout: state = {s3, s2, s1, s0}, s0 in bits [31:0]. Spec: docs/rtl/SPEC_v0.md section 5.6.
// GATED = 1: `clk` is a gated clock that only pulses in cycles with ld or adv (clk_gate in tim_top), so the enable is implicit
// and the state registers have no enable multiplexer; `adv` is then unused. GATED = 0: free-running clock with the enable (v0 / timing study v1).
module xoshiro128ss #(
    parameter GATED = 0
) (
    input  wire         clk,
    input  wire         ld,
    input  wire [127:0] ld_state,
    input  wire         adv,
    output wire [31:0]  out,
    output wire [127:0] state
);
    reg [31:0] s0, s1, s2, s3;

    // out = rotl(s1 * 5, 7) * 9 (multiplications by 5 and 9 are shift-and-add)
    wire [31:0] m5 = s1 + (s1 << 2);
    wire [31:0] r7 = {m5[24:0], m5[31:25]};
    assign out = r7 + (r7 << 3);

    // next state
    wire [31:0] t  = s1 << 9;
    wire [31:0] a2 = s2 ^ s0;
    wire [31:0] a3 = s3 ^ s1;
    wire [31:0] n1 = s1 ^ a2;
    wire [31:0] n0 = s0 ^ a3;
    wire [31:0] n2 = a2 ^ t;
    wire [31:0] n3 = {a3[20:0], a3[31:21]};   // rotl(a3, 11)

    always @(posedge clk) begin
        if (ld) begin
            s0 <= ld_state[31:0];
            s1 <= ld_state[63:32];
            s2 <= ld_state[95:64];
            s3 <= ld_state[127:96];
        end else if (adv || GATED != 0) begin
            s0 <= n0;
            s1 <= n1;
            s2 <= n2;
            s3 <= n3;
        end
    end

    assign state = {s3, s2, s1, s0};
endmodule
