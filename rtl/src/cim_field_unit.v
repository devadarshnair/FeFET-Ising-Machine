// CiM local-field unit (P3.03; golden: scripts/golden/cim_field.py). Models an analog crossbar MAC with a b-bit ADC.
//   P = P+ - P- (differential pair); each part is stored as WB one-bit planes, one column per (polarity, plane, lane):
//   column c = (pol*WB + plane)*N + lane holds, for each row j, bit `plane` of max(+-P[lane][j], 0). On `ld` every
//   column sums its active rows (x_j = 1), an optional additive noise (NOISE = 1) perturbs the sum, the ADC rounds
//   it to LSB = 2^s (the smallest s for which the rounded full scale FS fits `adc_bits` bits) and clips it to
//   0 .. 2^bits - 1, and the shift-add rebuilds h_i = d_i + sum_p 2^p (code+ - code-) << s. The result is registered
//   (h) and holds until the next ld (it doubles as the I10 field cache).
// Full scale FS = adc_fs (I7v2: the host programs the largest column sum of the array, golden cim_field.max_column_sum),
// or N rows when adc_fs = 0 (v1 behaviour, bit-identical to the design before I7v2).
// Noise (NOISE = 1): one 32-bit xorshift32 per column, initialised on ld_seed to seed ^ (c * 32'h9E3779B1) (0 -> 1),
// advanced once per conversion; s = sum of the four bytes of the new state; noise = ((s - 510) * sg) >>> 8 in units
// of 1/256 cell current. code = (sum*256 + noise + LSB*128) >>> (shift + 8). With NOISE = 0, or sg = 0, the noise is 0.
// Array writes: wr_p with the coupling P[wr_row][wr_col] = wr_val (JW bit signed).
// verilator lint_off WIDTHEXPAND   // behavioural CiM model (not synthesised, run.sh/Icarus/Verilator only): integer arithmetic in 32/64 b
// verilator lint_off WIDTHTRUNC   // behavioural CiM model: results are narrowed to the field width after explicit saturation
// verilator lint_off BLKSEQ   // behavioural CiM model: the column sum is a sequential while-loop with blocking temporaries; not synthesisable by design (see P3.09 n/a)
module cim_field_unit #(
    parameter N     = 16,
    parameter LOG2N = $clog2(N),
    parameter WB    = 8,
    parameter JW    = 8,
    parameter BW    = 8,
    parameter HW    = 18,
    parameter NOISE = 0
) (
    input  wire                clk,
    input  wire                wr_p,
    input  wire [LOG2N-1:0]    wr_row,
    input  wire [LOG2N-1:0]    wr_col,
    input  wire [JW-1:0]       wr_val,
    input  wire                ld_seed,
    input  wire [31:0]         seed,
    input  wire [15:0]         sg,
    input  wire [4:0]          adc_bits,
    input  wire [15:0]         adc_fs,
    input  wire [N-1:0]        x,
    input  wire [N*BW-1:0]     d,
    input  wire                ld,
    output reg  [N*HW-1:0]     h
);
    localparam NC = 2 * WB * N;

    reg [N-1:0]  col [0:NC-1];
    reg [31:0]   lf  [0:NC-1];

    // ---- array write
    reg signed [JW:0] wv;
    reg [JW:0]        mag;
    integer           wp;
    always @(posedge clk) begin
        if (wr_p) begin
            wv  = {wr_val[JW-1], wr_val};
            mag = wv[JW] ? -wv : wv;
            for (wp = 0; wp < WB; wp = wp + 1) begin
                col[wp * N + wr_row][wr_col]        <= !wv[JW] && (wv != 0) && mag[wp];
                col[(WB + wp) * N + wr_row][wr_col] <= wv[JW] && mag[wp];
            end
        end
    end

    // ---- conversion
    integer          shift, top, lsb, fsc;
    integer          pol, pl, ln, jj, c, sum;
    integer          code, acc;
    integer          bsum;
    reg [31:0]       st;
    integer          nz;
    reg signed [63:0] an;
    reg signed [N*HW-1:0] hnew;
    reg signed [BW-1:0]   dv;

    always @(posedge clk) begin
        if (NOISE != 0 && ld_seed) begin
            for (c = 0; c < NC; c = c + 1)
                lf[c] <= ((seed ^ (c * 32'h9E3779B1)) == 32'd0) ? 32'd1 : (seed ^ (c * 32'h9E3779B1));
        end
        if (ld) begin
            top   = (1 << adc_bits) - 1;
            fsc   = (adc_fs == 16'd0) ? N : adc_fs;
            shift = 0;
            while (((fsc + ((1 << shift) >> 1)) >> shift) > top) shift = shift + 1;
            lsb = 1 << shift;
            hnew = {N*HW{1'b0}};
            for (ln = 0; ln < N; ln = ln + 1) begin
                dv  = d[ln*BW +: BW];
                acc = dv;
                for (pol = 0; pol < 2; pol = pol + 1)
                    for (pl = 0; pl < WB; pl = pl + 1) begin
                        c   = (pol * WB + pl) * N + ln;
                        sum = 0;
                        for (jj = 0; jj < N; jj = jj + 1)
                            sum = sum + (col[c][jj] & x[jj]);
                        an = sum * 256;
                        if (NOISE != 0) begin
                            st = lf[c];
                            st = st ^ (st << 13);
                            st = st ^ (st >> 17);
                            st = st ^ (st << 5);
                            lf[c] <= st;
                            bsum = st[7:0] + st[15:8] + st[23:16] + st[31:24];
                            nz = ((bsum - 510) * $signed({1'b0, sg})) >>> 8;
                            an = an + nz;
                        end
                        an   = (an + lsb * 128) >>> (shift + 8);
                        code = (an < 0) ? 0 : ((an > top) ? top : an);
                        if (pol == 0) acc = acc + ((code << shift) << pl);
                        else          acc = acc - ((code << shift) << pl);
                    end
                hnew[ln*HW +: HW] = acc;
            end
            h <= hnew;
        end
    end
endmodule
// verilator lint_on WIDTHEXPAND
// verilator lint_on WIDTHTRUNC
// verilator lint_on BLKSEQ
