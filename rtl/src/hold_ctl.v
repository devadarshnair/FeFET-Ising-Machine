// Lane-generator advance control (tweaks I11 and I5). The per-lane generators advance once per step (acc_ld) in the v0 machine.
//   I11 greedy: the lane generators are unused and never advance.
//   I5 noise hold: a noise word is held for `hold` steps; the generators advance only after the last step of a window
//   (hold = 1: every step, equal to the v0 machine). Golden: scripts/golden/tweaks.py (TweakUnit.draw).
module hold_ctl (
    input  wire        clk,
    input  wire        init,
    input  wire        acc_ld,
    input  wire        i11,
    input  wire        i5,
    input  wire [15:0] hold,
    output wire        lane_adv
);
    reg  [15:0] cnt;
    wire        last = (cnt + 16'd1 >= hold);
    assign lane_adv = ~i11 & (~i5 | last);
    always @(posedge clk) begin
        if (init)
            cnt <= 16'd0;
        else if (acc_ld && i5)
            cnt <= last ? 16'd0 : cnt + 16'd1;
    end
endmodule
