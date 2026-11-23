// Global temperature register T (UQ16.16, energy LSB). "load" sets T = t0. At each step, if geom = 1,
// T = (T * alpha) >> 32 with alpha in UQ0.32 (per-step geometric schedule, SPEC section 5.5); if geom = 0, T holds.
// verilator lint_off UNUSEDSIGNAL   // T' is the high word of the 64 b T*alpha product (UQ0.32 alpha)
module temp_sched (
    input  wire        clk,
    input  wire        load,
    input  wire [31:0] t0,
    input  wire        step,
    input  wire        geom,
    input  wire [31:0] alpha,
    output reg  [31:0] temp
);
    wire [63:0] prod = temp * alpha;

    always @(posedge clk) begin
        if (load)
            temp <= t0;
        else if (step && geom)
            temp <= prod[63:32];
    end
endmodule
// verilator lint_on UNUSEDSIGNAL
