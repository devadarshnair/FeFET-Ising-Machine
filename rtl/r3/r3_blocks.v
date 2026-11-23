// Round 3 (round-3 design notes section 5, option B): RTL of the digital T-1 / T-6 / screening blocks, for synthesis only (Yosys + OpenSTA,
// Nangate45 typical; rtl/r3/run_round3.sh). The analog parts (1-bit FeFET row sense, verify read, re-erase) stay SPICE / literature.

// One T-1 lane: the 4 sensed bits of the flipped row (w = 2 planes x 2 polarities) form a 3-bit signed increment, which field_unit adds
// to the 16-bit field register (ONE add per lane per accepted flip). The lane clock is gated by the row-change mask bit (T-6), so an
// unchanged lane draws only its clock gate.
module r3_lane_t1 #(parameter HW = 16) (
    input  wire          clk,
    input  wire          init,
    input  wire [7:0]    bias,
    input  wire          upd,          // an accepted flip is being applied this cycle
    input  wire          dir,          // flipped spin goes 0 -> 1
    input  wire          chg,          // row-change mask: this lane's coupling to the flipped spin is non-zero
    input  wire [3:0]    sbits,        // sensed bits {neg1, pos1, neg0, pos0}
    output wire [HW-1:0] h,
    output wire          ovf
);
    wire signed [2:0] inc = $signed({1'b0, sbits[0]}) - $signed({1'b0, sbits[1]}) + ($signed({1'b0, sbits[2]}) <<< 1) - ($signed({1'b0, sbits[3]}) <<< 1);
    wire gclk;
    clk_gate u_cg (.clk(clk), .en(init | (upd & chg)), .gclk(gclk));
    field_unit #(.JW(3), .BW(8), .HW(HW)) u_f (.clk(gclk), .init(init), .bias(bias), .upd(upd & chg), .dir(dir), .pk(inc), .h(h), .ovf(ovf));
endmodule

// Same lane without gating (T-1 alone): reference for the T-6 saving.
module r3_lane_t1_ungated #(parameter HW = 16) (
    input  wire          clk,
    input  wire          init,
    input  wire [7:0]    bias,
    input  wire          upd,
    input  wire          dir,
    input  wire [3:0]    sbits,
    output wire [HW-1:0] h,
    output wire          ovf
);
    wire signed [2:0] inc = $signed({1'b0, sbits[0]}) - $signed({1'b0, sbits[1]}) + ($signed({1'b0, sbits[2]}) <<< 1) - ($signed({1'b0, sbits[3]}) <<< 1);
    field_unit #(.JW(3), .BW(8), .HW(HW)) u_f (.clk(clk), .init(init), .bias(bias), .upd(upd), .dir(dir), .pk(inc), .h(h), .ovf(ovf));
endmodule

// Spare-row remap: S entries {valid, retired row index}; a row read whose address hits an entry is redirected to spare row s.
module r3_remap #(parameter N = 512, parameter S = 16, parameter LOG2N = $clog2(N), parameter LOG2S = $clog2(S)) (
    input  wire             clk,
    input  wire             wr,
    input  wire [LOG2S-1:0] wsel,
    input  wire [LOG2N-1:0] wrow,
    input  wire [LOG2N-1:0] row,
    output reg              hit,
    output reg  [LOG2S-1:0] spare
);
    reg [LOG2N-1:0] idx [0:S-1];
    reg [S-1:0]     vld;
    integer i;
    always @(posedge clk) if (wr) begin idx[wsel] <= wrow; vld[wsel] <= 1'b1; end
    always @* begin
        hit = 1'b0; spare = {LOG2S{1'b0}};
        for (i = S - 1; i >= 0; i = i - 1)
            if (vld[i] && idx[i] == row) begin hit = 1'b1; spare = i[LOG2S-1:0]; end
    end
endmodule

// Leaky-zero screening sequencer (one-time): walks rows x columns, compares the verify-read ADC code with the cutoff, re-erases up to
// TRIES times, then requests a retire (remap) for the row. Digital control only; the verify read and erase pulse are analog.
module r3_screen_ctl #(parameter N = 512, parameter LOG2N = $clog2(N), parameter CB = 8) (
    input  wire          clk,
    input  wire          rst_n,
    input  wire          start,
    input  wire [CB-1:0] cutoff,
    input  wire [CB-1:0] code,       // verify-read result of the addressed cell
    input  wire          code_vld,
    output reg  [LOG2N-1:0] row,
    output reg  [LOG2N-1:0] col,
    output reg           erase,
    output reg           verify,
    output reg           retire,
    output reg           done
);
    reg [1:0] tries;
    reg [1:0] st;
    localparam S_IDLE = 2'd0, S_VER = 2'd1, S_ERS = 2'd2;
    always @(posedge clk) begin
        if (!rst_n) begin st <= S_IDLE; row <= 0; col <= 0; tries <= 0; erase <= 0; verify <= 0; retire <= 0; done <= 0; end
        else begin
            erase <= 0; verify <= 0; retire <= 0;
            case (st)
                S_IDLE: if (start) begin st <= S_VER; done <= 0; verify <= 1; end
                S_VER: if (code_vld) begin
                    if (code > cutoff && tries != 2'd3) begin st <= S_ERS; erase <= 1; tries <= tries + 2'd1; end
                    else begin
                        if (code > cutoff) retire <= 1;
                        tries <= 0;
                        if (col == N - 1) begin col <= 0; if (row == N - 1) begin st <= S_IDLE; done <= 1; end else row <= row + 1'b1; end
                        else col <= col + 1'b1;
                        verify <= 1;
                    end
                end
                S_ERS: begin st <= S_VER; verify <= 1; end
                default: st <= S_IDLE;
            endcase
        end
    end
endmodule

// Per-column correction table in flops: K entries {valid, row index}; a sensed '1' of a listed (known-leaky) row is forced to 0.
module r3_lcor_col #(parameter N = 512, parameter K = 4, parameter LOG2N = $clog2(N)) (
    input  wire             clk,
    input  wire             wr,
    input  wire [$clog2(K)-1:0] wsel,
    input  wire [LOG2N-1:0] wrow,
    input  wire [LOG2N-1:0] row,
    input  wire             sbit,
    output wire             obit
);
    reg [LOG2N-1:0] idx [0:K-1];
    reg [K-1:0]     vld;
    always @(posedge clk) if (wr) begin idx[wsel] <= wrow; vld[wsel] <= 1'b1; end
    wire [K-1:0] m;
    genvar g;
    generate for (g = 0; g < K; g = g + 1) begin : c
        assign m[g] = vld[g] && idx[g] == row;
    end endgenerate
    assign obit = sbit & ~|m;
endmodule
