// timing study v1 (timing/area) synthesis-only wrappers. Same logic as syn_lane_logic (rtl/synth/synth_wrappers.v) with the I11
// greedy pin left free (the confirmed datapath can switch greedy acceptance on), so timing covers both acceptance modes.
module tt_lane_i11 #(
    parameter NSEG = 1, parameter CW = 7, parameter TW = 7, parameter LW = 12,
    parameter HW = 18, parameter EW = 24, parameter JW = 10, parameter BW = 12
) (
    input  wire               clk,
    input  wire               init,
    input  wire               flip,
    input  wire               dir,
    input  wire               cnt_add_ld,
    input  wire               cnt_rem_ld,
    input  wire [NSEG*CW-1:0] seg_cnt,
    input  wire               x,
    input  wire [HW-1:0]      h_acc,
    input  wire [15:0]        lam,
    input  wire [2:0]         gsh,
    input  wire [EW-1:0]      eoff,
    input  wire [31:0]        temp,
    input  wire [JW-1:0]      pk,
    input  wire [BW-1:0]      bias,
    input  wire [LW-1:0]      lval,
    input  wire               greedy,
    output wire [HW-1:0]      h,
    output wire [HW-1:0]      gain,
    output wire               acc,
    output reg  [TW-1:0]      cnt_add,
    output reg  [TW-1:0]      cnt_rem,
    output wire               ovf
);
    field_unit #(.JW(JW), .BW(BW), .HW(HW)) u_field (
        .clk(clk), .init(init), .bias(bias), .upd(flip), .dir(dir), .pk(pk), .h(h), .ovf(ovf)
    );
    wire [TW-1:0] tot;
    seg_adder #(.NROW(1), .NSEG(NSEG), .CW(CW), .TW(TW)) u_sum (.r_cnt(seg_cnt), .tot(tot));
    always @(posedge clk) begin
        if (init) begin
            cnt_add <= {TW{1'b0}};
            cnt_rem <= {TW{1'b0}};
        end else begin
            if (cnt_add_ld) cnt_add <= tot;
            if (cnt_rem_ld) cnt_rem <= tot;
        end
    end
    accept_unit #(.HW(HW), .TW(TW), .LW(LW), .EW(EW)) u_acc (
        .h(h), .h_acc(h_acc), .x(x), .cnt_add(cnt_add), .cnt_rem(cnt_rem), .lam(lam), .gsh(gsh), .eoff(eoff),
        .temp(temp), .lval(lval), .greedy(greedy), .gain(gain), .acc(acc)
    );
endmodule

// timing study v2: the library integrated clock gate (Nangate45 CLKGATETST_X1: latch + AND) that clk_gate.v models in RTL; power / area of the gate that
// gates the lane generators (shared by all N lane generators) and the selection generator. Needs `read_liberty -lib` (LIBCELLS = 1).
module tt_icg (
    input  wire CK,
    input  wire E,
    output wire GCK
);
    CLKGATETST_X1 u_icg (.CK(CK), .E(E), .SE(1'b0), .GCK(GCK));
endmodule
