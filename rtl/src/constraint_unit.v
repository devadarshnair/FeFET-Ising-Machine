// Constraint unit (knapsack mode): weight memory W, capacities C, load registers L, slacks and the
// feasibility of the state after the pending flip (SPEC sections 5.1 and 5.4).
// Constraint j owns a memory of N words of WW bits: word k = w_jk. A read of item k happens in all constraints at
// once (registered, one cycle after rd_en). upd (with en = knapsack mode) applies L_j += w_jk (dir = 1) or
// L_j -= w_jk (dir = 0). feas_next = all_j (L_j +- w_jk <= C_j) for the word that was read; it is 1 when en = 0.
// verilator lint_off WIDTHEXPAND   // 6 b item weight added to the 16 b load register (zero extension)
module constraint_unit #(
    parameter N     = 64,
    parameter LOG2N = $clog2(N),
    parameter NCON  = 8,
    parameter WW    = 6,
    parameter LDW   = 16
) (
    input  wire                     clk,
    input  wire                     wr_w,
    input  wire                     wr_c,
    input  wire [3:0]               wr_con,
    input  wire [LOG2N-1:0]         wr_item,
    input  wire [15:0]              wr_data,
    input  wire                     clr,
    input  wire                     rd_en,
    input  wire [LOG2N-1:0]         rd_item,
    input  wire                     upd,
    input  wire                     dir,
    input  wire                     en,
    output wire [NCON*LDW-1:0]      load,
    output wire [NCON*(LDW+1)-1:0]  slack,
    output wire                     feas_next
);
    wire [NCON-1:0] ok_next;

    genvar j;
    generate
        for (j = 0; j < NCON; j = j + 1) begin : con
            reg [WW-1:0]  wmem [0:N-1];
            reg [WW-1:0]  wq;
            reg [LDW-1:0] cap;
            reg [LDW-1:0] ld;
            wire [LDW-1:0] ld_next = dir ? (ld + wq) : (ld - wq);
            always @(posedge clk) begin
                if (wr_w && wr_con == j)
                    wmem[wr_item] <= wr_data[WW-1:0];
                if (wr_c && wr_con == j)
                    cap <= wr_data[LDW-1:0];
                if (rd_en)
                    wq <= wmem[rd_item];
                if (clr)
                    ld <= {LDW{1'b0}};
                else if (upd && en)
                    ld <= ld_next;
            end
            assign load[j*LDW +: LDW]            = ld;
            assign slack[j*(LDW+1) +: (LDW+1)]   = {1'b0, cap} - {1'b0, ld};
            assign ok_next[j]                    = (ld_next <= cap);
        end
    endgenerate

    assign feas_next = ~en | (&ok_next);
endmodule
// verilator lint_on WIDTHEXPAND
