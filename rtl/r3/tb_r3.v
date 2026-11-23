// Self-checking testbench of the round-3 blocks (tests/hw/test_round3.py runs it with Icarus).
`timescale 1ns/1ps
module tb_r3;
    reg clk = 0; always #1 clk = ~clk;
    reg init, upd, dir, chg; reg [3:0] sb; reg [7:0] bias;
    wire [15:0] h; wire ovf;
    r3_lane_t1 dut (.clk(clk), .init(init), .bias(bias), .upd(upd), .dir(dir), .chg(chg), .sbits(sb), .h(h), .ovf(ovf));
    reg [8:0] row; reg wr; reg [3:0] wsel; reg [8:0] wrow; wire hit; wire [3:0] sp;
    r3_remap #(.N(512), .S(16)) rm (.clk(clk), .wr(wr), .wsel(wsel), .wrow(wrow), .row(row), .hit(hit), .spare(sp));
    reg lw; reg [1:0] lsel; reg [8:0] lrow; reg sbit; wire obit;
    r3_lcor_col #(.N(512), .K(4)) lc (.clk(clk), .wr(lw), .wsel(lsel), .wrow(lrow), .row(row), .sbit(sbit), .obit(obit));
    integer err = 0, exp;
    task step(input u, input d, input c, input [3:0] s); begin upd = u; dir = d; chg = c; sb = s; @(posedge clk); #0.1; end endtask
    initial begin
        init = 1; upd = 0; dir = 0; chg = 0; sb = 0; bias = 8'sd5; wr = 0; lw = 0; row = 0; sbit = 1; wsel = 0; wrow = 0; lsel = 0; lrow = 0;
        @(posedge clk); #0.1; init = 0;
        if ($signed(h) != 5) err = err + 1;
        step(1, 1, 1, 4'b0101); exp = 5 + 3;           // pos0 + 2 pos1 = +3
        if ($signed(h) != exp) err = err + 1;
        step(1, 0, 1, 4'b0101); exp = 5;                // reverse flip
        if ($signed(h) != exp) err = err + 1;
        step(1, 1, 0, 4'b0101);                          // gated: chg = 0 leaves h
        if ($signed(h) != exp) err = err + 1;
        step(1, 1, 1, 4'b1010); exp = 5 - 3;            // neg0 + 2 neg1 = -3
        if ($signed(h) != exp) err = err + 1;
        step(0, 1, 1, 4'b1111);                          // no upd
        if ($signed(h) != exp) err = err + 1;
        wr = 1; wsel = 3; wrow = 9'd77; @(posedge clk); #0.1; wr = 0;
        row = 9'd77; #0.1; if (!hit || sp != 3) err = err + 1;
        row = 9'd78; #0.1; if (hit) err = err + 1;
        lw = 1; lsel = 1; lrow = 9'd200; @(posedge clk); #0.1; lw = 0;
        row = 9'd200; sbit = 1; #0.1; if (obit) err = err + 1;
        row = 9'd201; #0.1; if (!obit) err = err + 1;
        if (err == 0) $display("R3TB PASS"); else $display("R3TB FAIL %0d", err);
        $finish;
    end
endmodule
