// One lane of the machine (one spin): its coupling row and bias, its local field, its acceptance LUT copy and
// acceptance unit, the segment adder for its TCAM row, and its two count registers.
// The lane's random number (rnd) comes from its own xoshiro128** generator in tim_top.
// Keeping each lane's signals on its own nets (no shared N-wide buses on the per-step path) keeps simulation time
// linear in N per lane; see the note on Icarus speed in docs/rtl/STATUS.md.
// verilator lint_off UNUSEDSIGNAL   // only the top LAB bits of the lane random word address the acceptance LUT
module tim_lane #(
    parameter N     = 64,
    parameter LOG2N = $clog2(N),
    parameter NSEG  = 1,
    parameter CW    = 7,
    parameter TW    = 7,
    parameter LAB   = 10,
    parameter LW    = 12,
    parameter HW    = 18,
    parameter EW    = 24,
    parameter JW    = 8,
    parameter BW    = 8,
    parameter DW    = (JW > BW) ? JW : BW
) (
    input  wire               clk,
    // host writes (wr_p / wr_b are already decoded for this lane)
    input  wire               wr_p,
    input  wire               wr_b,
    input  wire [LOG2N-1:0]   wr_col,
    input  wire [DW-1:0]      wr_data,
    input  wire               wr_lut,
    input  wire [LAB-1:0]     wr_lut_addr,
    input  wire [LW-1:0]      wr_lut_data,
    // step control
    input  wire               init,
    input  wire               rd_en,
    input  wire [LOG2N-1:0]   rd_col,
    input  wire               flip,
    input  wire               dir,
    input  wire               cnt_add_ld,
    input  wire               cnt_rem_ld,
    input  wire [NSEG*CW-1:0] seg_cnt,
    // global values
    input  wire               x,
    input  wire [HW-1:0]      h_acc,
    input  wire [15:0]        lam,
    input  wire [2:0]         gsh,
    input  wire [EW-1:0]      eoff,
    input  wire [31:0]        temp,
    input  wire [31:0]        rnd,
    input  wire               greedy,     // I11: acceptance without the threshold term and the offset
    // outputs
    output wire [HW-1:0]      h,
    output wire [BW-1:0]      bias_o,
    output wire [HW-1:0]      gain,
    output wire               acc,
    output reg  [TW-1:0]      cnt_add,
    output reg  [TW-1:0]      cnt_rem,
    output wire               ovf
);
    wire [JW-1:0] pk;
    wire [BW-1:0] bias;
    coupling_mem #(.N(N), .JW(JW), .BW(BW)) u_cmem (
        .clk(clk), .wr_p(wr_p), .wr_b(wr_b), .wr_col(wr_col), .wr_data(wr_data),
        .rd_en(rd_en), .rd_col(rd_col), .pk(pk), .bias(bias)
    );

    field_unit #(.JW(JW), .BW(BW), .HW(HW)) u_field (
        .clk(clk), .init(init), .bias(bias), .upd(flip), .dir(dir), .pk(pk), .h(h), .ovf(ovf)
    );

    assign bias_o = bias;
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

    wire [LW-1:0] lval;
    accept_lut #(.LAB(LAB), .LW(LW)) u_lut (
        .clk(clk), .wr(wr_lut), .wr_addr(wr_lut_addr), .wr_data(wr_lut_data), .rd_addr(rnd[31:32-LAB]),
        .rd_data(lval)
    );

    accept_unit #(.HW(HW), .TW(TW), .LW(LW), .EW(EW)) u_acc (
        .h(h), .h_acc(h_acc), .x(x), .cnt_add(cnt_add), .cnt_rem(cnt_rem), .lam(lam), .gsh(gsh), .eoff(eoff), .temp(temp),
        .lval(lval), .greedy(greedy), .gain(gain), .acc(acc)
    );
endmodule
// verilator lint_on UNUSEDSIGNAL
