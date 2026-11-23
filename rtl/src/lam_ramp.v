// I3 ramped penalty gain: lam_t = lam_lo + floor((lam - lam_lo) * min(t, ramp) / ramp), t = 1, 2, ... (golden tweaks.py).
// Division-free: with D = lam - lam_lo = dq * ramp + dr (the host writes dq and dr, 0 <= dr < ramp), the quotient is
// accumulated step by step: q += dq, rem += dr, and one extra count when rem reaches ramp. One update per step while
// t < ramp (a 16 b adder, a 32 b adder-subtractor and a step compare), then lam_t holds at lam. init loads t = 1.
module lam_ramp (
    input  wire        clk,
    input  wire        init,
    input  wire        step,        // one pulse per machine step (UPD)
    input  wire [15:0] lam_lo,
    input  wire [31:0] ramp,        // ramp_steps >= 1
    input  wire [15:0] dq,
    input  wire [31:0] dr,
    output wire [15:0] lam_t
);
    reg  [15:0] q;
    reg  [31:0] rem;
    reg  [31:0] t;
    wire [32:0] rsum  = {1'b0, rem} + {1'b0, dr};
    wire        carry = (rsum >= {1'b0, ramp});
    assign lam_t = lam_lo + q;

    always @(posedge clk) begin
        if (init) begin
            q   <= dq;
            rem <= dr;
            t   <= 32'd1;
        end else if (step && t < ramp) begin
            q   <= q + dq + {15'd0, carry};
            rem <= carry ? rsum[31:0] - ramp : rsum[31:0];
            t   <= t + 32'd1;
        end
    end
endmodule
