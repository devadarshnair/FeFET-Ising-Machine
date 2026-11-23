// Behavioural digital stand-in TCAM behind the pricer interface (SPEC section 8). We own this model.
// It is also the plan's C2 control: the TCAM function computed by exact digital logic, same interface.
// The FeFET transistor-level array (G4/G5) will later replace it through the same ports, with latency, energy and
// error rates taken from our own SPICE runs.
//
// Storage: per row and segment, SEGW stored bits and SEGW care bits (ternary).
// Write port: a write is taken when wr_en = 1 and wr_busy = 0; wr_busy is then 1 for WRITE_LAT cycles.
//   A write while busy is dropped and counted in n_wdrop.
// Search port: s_valid for one cycle with key, mask (1 = compare this column, 0 = X) and row enables.
//   s_done is 1 exactly SEARCH_LAT cycles after the s_valid cycle; r_cnt changes only then and holds until the next
//   result. One search at a time: a new s_valid must not come before s_done.
//   Count of row r, segment g = popcount((bits XOR key) AND care AND mask) if row r is enabled, else 0.
// Hooks: event counters for the energy model; count-error injection (ERR_HOOK = 1): each (row, segment) has an
//   xorshift32 that advances on every result; if err_en = 1 and the row is enabled and rnd[15:0] < err_thr, the
//   count becomes count + 1 (rnd[16] = 1) or count - 1 (rnd[16] = 0), clamped to 0..SEGW. n_err counts changed counts.
// verilator lint_off WIDTHEXPAND   // 32/48 b statistics counters add 16 b popcount results
module tcam_stub #(
    parameter NROW       = 64,
    parameter RW         = $clog2(NROW),
    parameter SEGW       = 64,
    parameter NSEG       = 1,
    parameter SGW        = (NSEG > 1) ? $clog2(NSEG) : 1,
    parameter CW         = 7,
    parameter SEARCH_LAT = 2,
    parameter WRITE_LAT  = 4,
    parameter ERR_HOOK   = 1
) (
    input  wire                      clk,
    input  wire                      rst_n,
    // write port
    input  wire                      wr_en,
    input  wire [RW-1:0]             wr_row,
    input  wire [SGW-1:0]            wr_seg,
    input  wire [SEGW-1:0]           wr_bits,
    input  wire [SEGW-1:0]           wr_care,
    output wire                      wr_busy,
    // search port
    input  wire                      s_valid,
    input  wire [NSEG*SEGW-1:0]      s_key,
    input  wire [NSEG*SEGW-1:0]      s_mask,
    input  wire [NROW-1:0]           s_row_en,
    output reg                       s_done,
    output reg  [NROW*NSEG*CW-1:0]   r_cnt,
    // hooks
    input  wire                      err_en,
    input  wire [15:0]               err_thr,
    output reg  [31:0]               n_search,
    output reg  [31:0]               n_write,
    output reg  [31:0]               n_wdrop,
    output reg  [31:0]               n_err,
    output reg  [47:0]               n_rows_en,
    output reg  [47:0]               n_cells
);
    localparam KW = NSEG * SEGW;
    localparam NC = NROW * NSEG;            // number of (row, segment) words

    // ---------------------------------------------------------------- write side
    reg [7:0] wcnt;
    assign wr_busy = (wcnt != 8'd0);
    wire wr_take = wr_en && !wr_busy;

    always @(posedge clk) begin
        if (!rst_n) begin
            wcnt    <= 8'd0;
            n_write <= 32'd0;
            n_wdrop <= 32'd0;
        end else if (wr_take) begin
            wcnt    <= WRITE_LAT;
            n_write <= n_write + 32'd1;
        end else begin
            if (wr_en)
                n_wdrop <= n_wdrop + 32'd1;
            if (wcnt != 8'd0)
                wcnt <= wcnt - 8'd1;
        end
    end

    // ---------------------------------------------------------------- search request and latency
    reg [KW-1:0]   q_key;
    reg [KW-1:0]   q_mask;
    reg [NROW-1:0] q_en;
    reg [7:0]      lat;
    reg            pending;

    wire           direct = (SEARCH_LAT == 1);
    wire [KW-1:0]  e_key  = direct ? s_key    : q_key;
    wire [KW-1:0]  e_mask = direct ? s_mask   : q_mask;
    wire [NROW-1:0] e_en  = direct ? s_row_en : q_en;
    wire           fire   = direct ? s_valid  : (pending && lat == 8'd1);

    function [15:0] popc_rows;
        input [NROW-1:0] v;
        integer b;
        begin
            popc_rows = 16'd0;
            for (b = 0; b < NROW; b = b + 1)
                popc_rows = popc_rows + v[b];
        end
    endfunction

    function [15:0] popc_key;
        input [KW-1:0] v;
        integer b;
        begin
            popc_key = 16'd0;
            for (b = 0; b < KW; b = b + 1)
                popc_key = popc_key + v[b];
        end
    endfunction

    function [CW-1:0] popc_seg;
        input [SEGW-1:0] v;
        integer b;
        begin
            popc_seg = {CW{1'b0}};
            for (b = 0; b < SEGW; b = b + 1)
                popc_seg = popc_seg + v[b];
        end
    endfunction

    // ---------------------------------------------------------------- storage and per-word count
    wire [NC*CW-1:0] cnt_new;     // counts after error injection, for the request being answered
    wire [NC-1:0]    inj;         // this word's count was changed by the error hook

    genvar r, g;
    generate
        for (r = 0; r < NROW; r = r + 1) begin : row
            for (g = 0; g < NSEG; g = g + 1) begin : seg
                reg [SEGW-1:0] bits;
                reg [SEGW-1:0] care;
                always @(posedge clk) begin
                    if (wr_take && wr_row == r && (NSEG == 1 || wr_seg == g)) begin
                        bits <= wr_bits;
                        care <= wr_care;
                    end
                end
                wire [SEGW-1:0] mis   = (bits ^ e_key[g*SEGW +: SEGW]) & care & e_mask[g*SEGW +: SEGW];
                wire [CW-1:0]   exact = e_en[r] ? popc_seg(mis) : {CW{1'b0}};
                if (ERR_HOOK) begin : err
                    reg  [31:0]   rs;
                    wire [31:0]   x1 = rs ^ (rs << 13);
                    wire [31:0]   x2 = x1 ^ (x1 >> 17);
                    wire [31:0]   x3 = x2 ^ (x2 << 5);
                    wire          hit = err_en && e_en[r] && (rs[15:0] < err_thr);
                    wire [CW-1:0] up  = (exact == SEGW) ? exact : exact + 1'b1;
                    wire [CW-1:0] dn  = (exact == 0) ? exact : exact - 1'b1;
                    wire [CW-1:0] bad = rs[16] ? up : dn;
                    always @(posedge clk) begin
                        if (!rst_n)
                            rs <= 32'h9E3779B9 ^ ((r * NSEG + g + 1) * 32'h85EBCA6B);
                        else if (fire)
                            rs <= x3;
                    end
                    assign cnt_new[(r*NSEG+g)*CW +: CW] = hit ? bad : exact;
                    assign inj[r*NSEG+g]                = hit && (bad != exact);
                end else begin : noerr
                    assign cnt_new[(r*NSEG+g)*CW +: CW] = exact;
                    assign inj[r*NSEG+g]                = 1'b0;
                end
            end
        end
    endgenerate

    function [15:0] popc_inj;
        input [NC-1:0] v;
        integer b;
        begin
            popc_inj = 16'd0;
            for (b = 0; b < NC; b = b + 1)
                popc_inj = popc_inj + v[b];
        end
    endfunction

    // ---------------------------------------------------------------- request, result and counters
    always @(posedge clk) begin
        if (!rst_n) begin
            s_done    <= 1'b0;
            pending   <= 1'b0;
            lat       <= 8'd0;
            n_search  <= 32'd0;
            n_err     <= 32'd0;
            n_rows_en <= 48'd0;
            n_cells   <= 48'd0;
        end else begin
            s_done <= fire;
            if (fire) begin
                r_cnt   <= cnt_new;
                n_err   <= n_err + popc_inj(inj);
                pending <= 1'b0;
            end
            if (s_valid) begin
                q_key     <= s_key;
                q_mask    <= s_mask;
                q_en      <= s_row_en;
                pending   <= !direct;
                lat       <= SEARCH_LAT - 1;
                n_search  <= n_search + 32'd1;
                n_rows_en <= n_rows_en + popc_rows(s_row_en);
                n_cells   <= n_cells + popc_rows(s_row_en) * popc_key(s_mask);
            end else if (pending) begin
                lat <= lat - 8'd1;
            end
        end
    end
endmodule
// verilator lint_on WIDTHEXPAND
