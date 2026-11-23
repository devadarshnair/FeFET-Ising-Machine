// Stall-gated array/ADC power (I10) and stall-adaptive ADC precision (I7), P3.04. Golden: scripts/golden/power.py.
// Stall counter: consecutive steps without a strict improvement of the best-so-far feasible objective, updated at the
// end of every step (after a restart too), never reset by a restart (unlike the restart arm's own counter).
//   I10  a step reuses the field register of the CiM unit instead of reading the array when no flip and no restart
//        happened since the last read and the ADC precision did not change (skip_nx, evaluated in the cycle that ends
//        the previous step, so a skipped read costs 0 cycles). While skipped with counter > K_g the ADC bias is gated.
//   I7   ADC bits = b_lo while counter > K_p, else b_hi (adc_bits changes at the step boundary).
// Outputs: arr_en (array read in progress), adc_en (ADC bias on), adc_bits, skip_nx, and cumulative activity counters.
module power_ctl #(
    parameter N  = 64,
    parameter WB = 8
) (
    input  wire        clk,
    input  wire        rst_n,
    input  wire        init,
    input  wire        i10,
    input  wire        i7,
    input  wire [15:0] kg,
    input  wire [15:0] kp,
    input  wire [4:0]  b_hi,
    input  wire [4:0]  b_lo,
    input  wire [4:0]  b_nom,
    input  wire        upd,
    input  wire        sel_valid,
    input  wire        trig,
    input  wire        fin,
    input  wire        imp_best,
    input  wire        kc2_best_upd,
    input  wire        acc_ld,
    input  wire        cim_ld,
    input  wire        cim_busy,
    output wire        skip_nx,
    output wire        arr_en,
    output wire        adc_en,
    output reg  [4:0]  adc_bits,
    output reg  [31:0] c_reads,
    output reg  [31:0] c_skipped,
    output reg  [31:0] c_cells,
    output reg  [31:0] c_conv,
    output reg  [31:0] c_convbits,
    output reg  [31:0] c_lowc,
    output reg  [31:0] c_lowb,
    output reg  [31:0] c_gated
);
    localparam [31:0] COLS = 2 * WB * N;

    reg [31:0] counter;
    reg        pimp;
    reg        valid;
    reg        skip_q;

    wire step_end     = (upd && !trig) || fin;
    wire improved     = pimp || imp_best || kc2_best_upd;
    wire [31:0] cnt_n = improved ? 32'd0 : counter + 32'd1;
    wire [4:0]  bits_n = i7 ? ((cnt_n > {16'd0, kp}) ? b_lo : b_hi) : b_nom;
    wire        valid_n = valid && !(upd && sel_valid);
    wire        prec_chg = (bits_n != adc_bits);
    assign skip_nx = i10 && !init && valid_n && !prec_chg;

    assign arr_en = cim_busy;
    assign adc_en = !(skip_q && (counter > {16'd0, kg}));

    always @(posedge clk) begin
        if (!rst_n) begin
            counter <= 32'd0; pimp <= 1'b0; valid <= 1'b0; skip_q <= 1'b0; adc_bits <= 5'd16;
        end else if (init) begin
            counter  <= 32'd0;
            pimp     <= 1'b0;
            valid    <= 1'b0;
            skip_q   <= 1'b0;
            adc_bits <= i7 ? b_hi : b_nom;
        end else begin
            if (imp_best || kc2_best_upd)
                pimp <= 1'b1;
            if (upd && (sel_valid || trig))
                valid <= 1'b0;
            if (cim_ld)
                valid <= 1'b1;
            if (step_end) begin
                counter  <= cnt_n;
                pimp     <= 1'b0;
                adc_bits <= bits_n;
                skip_q   <= skip_nx;
            end
        end
    end

    // activity counters (attributed to the step that performs or skips the read)
    always @(posedge clk) begin
        if (init || !rst_n) begin
            c_reads <= 0; c_skipped <= 0; c_cells <= 0; c_conv <= 0; c_convbits <= 0; c_lowc <= 0; c_lowb <= 0;
            c_gated <= 0;
        end else begin
            if (cim_ld) begin
                c_reads    <= c_reads + 32'd1;
                c_cells    <= c_cells + N * COLS;
                c_conv     <= c_conv + COLS;
                c_convbits <= c_convbits + COLS * adc_bits;
                if (adc_bits < b_nom) begin
                    c_lowc <= c_lowc + COLS;
                    c_lowb <= c_lowb + COLS * adc_bits;
                end
            end
            if (acc_ld && skip_q) begin
                c_skipped <= c_skipped + 32'd1;
                if (counter > {16'd0, kg})
                    c_gated <= c_gated + 32'd1;
            end
        end
    end
endmodule
