// Top-level controller of TIM v0 (SPEC section 4): the step FSM, the step counter, the objective f, and the
// best-so-far f, x and step. It also registers the selection result (valid, index, count) in state SEL.
//
// Step in QUBO mode:     ACC, SEL x SEL_LAT, RD, UPD                         = 3 + SEL_LAT cycles (4 for SEL_LAT = 1)
// Step in knapsack mode: QENC, SADD, WADD x SEARCH_LAT, SREM, WREM x SEARCH_LAT, ACC, SEL, RD, UPD
//                        = 6 + SEL_LAT + 2*SEARCH_LAT cycles (WADD/WREM wait for s_done from the TCAM)
// SEL_LAT > 1 only stretches state SEL (the pipelined select tree needs its inputs held); the selected spin is unchanged.
// verilator lint_off WIDTHEXPAND   // 18 b gain added to the 32 b objective (sign extension); seed counter vs the integer SEED_CYCLES constant
module tim_ctrl #(
    parameter CIM   = 0,
    parameter N     = 64,
    parameter LOG2N = $clog2(N),
    parameter HW    = 18,
    parameter SEL_LAT = 1     // cycles spent in S_SEL (pipelined select tree); 1 = the single-cycle tree of v0
) (
    input  wire                 clk,
    input  wire                 rst_n,
    input  wire                 start,
    input  wire                 knap,
    input  wire [31:0]          ksteps,
    input  wire                 s_done,
    // combinational selection result (from select_tree on the registered acc vector)
    input  wire                 sel_valid_c,
    input  wire [LOG2N-1:0]     sel_idx_c,
    input  wire [LOG2N:0]       sel_cnt_c,
    // gain of the registered selected lane, and the state needed for the best-so-far update
    input  wire signed [HW-1:0] gain_sel,
    input  wire [N-1:0]         x,
    input  wire                 feas_next,
    input  wire                 feas_now,
    // CiM read (state S_CIM, CIM = 1): duration in cycles, skip decision for the next step (I10), load strobe
    input  wire [5:0]           cim_dur,
    input  wire                 cim_skip_nx,
    output wire                 cim_ld,
    output reg  [15:0]          cim_cycles,
    // restart unit (S_RST): trigger in the UPD cycle, per-cycle strobes, completion
    input  wire                 rs_trig,
    input  wire                 rs_fin,
    input  wire                 rs_flip,
    input  wire                 rs_kc2_fin,
    output wire                 flipped_ok,
    output wire                 imp_best,
    output wire signed [31:0]   f_new_o,
    output reg  [15:0]          rs_cycles,
    // status
    output wire                 busy,
    output wire                 done,
    output reg  [3:0]           st,
    // strobes to the datapath
    output wire                 seed_init,
    output wire                 seed_shift,
    output wire                 init,
    output wire                 qenc_ld,
    output wire                 s_valid,
    output wire                 s_rem,
    output wire                 cnt_add_ld,
    output wire                 cnt_rem_ld,
    output wire                 acc_ld,
    output wire                 sel_ld,
    output wire                 rd_en,
    output wire                 upd,
    output wire                 flip,
    // registered results
    output reg                  sel_valid,
    output reg  [LOG2N-1:0]     sel_idx,
    output reg  [LOG2N:0]       nacc,
    output reg  [31:0]          step,
    output reg                  step_valid,
    output reg  signed [31:0]   f,
    output reg  signed [31:0]   best_f,
    output reg  [31:0]          best_step,
    output reg  [N-1:0]         best_x
);
    localparam [3:0] S_IDLE = 4'd0,  S_SEED = 4'd1,  S_INIT = 4'd2,  S_QENC = 4'd3,  S_SADD = 4'd4,
                     S_WADD = 4'd5,  S_SREM = 4'd6,  S_WREM = 4'd7,  S_ACC  = 4'd8,  S_SEL  = 4'd9,
                     S_RD   = 4'd10, S_UPD  = 4'd11, S_DONE = 4'd12, S_RST = 4'd13, S_CIM = 4'd14;
    localparam SEED_CYCLES = 2 * (N + 1);

    reg [LOG2N+2:0] seed_cnt;

    wire idle_like = (st == S_IDLE) || (st == S_DONE);
    assign busy       = !idle_like;
    assign done       = (st == S_DONE);
    assign seed_init  = idle_like && start;
    assign seed_shift = (st == S_SEED);
    assign init       = (st == S_INIT);
    assign qenc_ld    = (st == S_QENC);
    assign s_valid    = (st == S_SADD) || (st == S_SREM);
    assign s_rem      = (st == S_SREM);
    assign cnt_add_ld = (st == S_WADD) && s_done;
    assign cnt_rem_ld = (st == S_WREM) && s_done;
    assign acc_ld     = (st == S_ACC);
    reg  [3:0] sel_cyc;
    wire sel_last     = (SEL_LAT <= 1) ? 1'b1 : (sel_cyc == SEL_LAT - 1);
    assign sel_ld     = (st == S_SEL) && sel_last;
    assign rd_en      = (st == S_RD);
    assign upd        = (st == S_UPD);
    assign flip       = upd && sel_valid;

    wire [3:0]         pre_acc     = (CIM != 0 && !cim_skip_nx) ? S_CIM : S_ACC;
    wire [3:0]         first_state = knap ? S_QENC : pre_acc;
    reg  [5:0]         cim_cnt;
    reg  [15:0]        cim_cyc;
    wire               cim_last    = (st == S_CIM) && (cim_cnt + 6'd1 == cim_dur);
    assign cim_ld = cim_last;
    wire signed [31:0] f_new       = f + gain_sel;
    wire [N-1:0]       onehot      = {{(N-1){1'b0}}, 1'b1} << sel_idx;
    wire               last_step   = (step + 32'd1 == ksteps);
    assign flipped_ok = upd && sel_valid && feas_next;
    assign imp_best   = flipped_ok && (f_new > best_f);
    assign f_new_o    = f_new;

    always @(posedge clk) begin
        if (!rst_n) begin
            st         <= S_IDLE;
            sel_cyc    <= 4'd0;
            step_valid <= 1'b0;
            seed_cnt   <= 0;
        end else begin
            step_valid <= (upd && !rs_trig) || rs_fin;
            case (st)
                S_IDLE, S_DONE: if (start) begin
                    st       <= S_SEED;
                    seed_cnt <= 0;
                end
                S_SEED: begin
                    seed_cnt <= seed_cnt + 1'b1;
                    if (seed_cnt == SEED_CYCLES - 1)
                        st <= S_INIT;
                end
                S_INIT: st <= (ksteps == 32'd0) ? S_DONE : first_state;
                S_QENC: st <= S_SADD;
                S_SADD: st <= S_WADD;
                S_WADD: if (s_done) st <= S_SREM;
                S_SREM: st <= S_WREM;
                S_WREM: if (s_done) st <= pre_acc;
                S_CIM:  if (cim_last) st <= S_ACC;
                S_ACC:  st <= S_SEL;
                S_SEL:  begin
                    sel_cyc <= sel_last ? 4'd0 : sel_cyc + 4'd1;
                    if (sel_last) st <= S_RD;
                end
                S_RD:   st <= S_UPD;
                S_UPD:  st <= rs_trig ? S_RST : (last_step ? S_DONE : first_state);
                S_RST:  if (rs_fin) st <= (step == ksteps) ? S_DONE : first_state;
                default: st <= S_IDLE;
            endcase
        end
    end

    // datapath registers owned by the controller
    always @(posedge clk) begin
        if (init) begin
            step      <= 32'd0;
            f         <= 32'sd0;
            best_f    <= 32'sd0;
            best_step <= 32'd0;
            best_x    <= {N{1'b0}};
            sel_valid <= 1'b0;
            sel_idx   <= {LOG2N{1'b0}};
            nacc      <= {(LOG2N+1){1'b0}};
            rs_cycles <= 16'd0;
            cim_cnt   <= 6'd0;
            cim_cyc   <= 16'd0;
            cim_cycles <= 16'd0;
        end else begin
            if (sel_ld) begin
                sel_valid <= sel_valid_c;
                sel_idx   <= sel_idx_c;
                nacc      <= sel_cnt_c;
            end
            if (st == S_CIM) begin
                cim_cnt <= cim_last ? 6'd0 : cim_cnt + 6'd1;
                cim_cyc <= cim_cyc + 16'd1;
            end
            if (upd) begin
                cim_cycles <= cim_cyc;
                cim_cyc    <= 16'd0;
            end
            if (upd)
                rs_cycles <= 16'd0;
            else if (st == S_RST)
                rs_cycles <= rs_cycles + 16'd1;
            if (rs_flip)
                f <= f_new;
            if (rs_kc2_fin && feas_now && f > best_f) begin
                best_f    <= f;
                best_step <= step;
                best_x    <= x;
            end
            if (upd) begin
                step <= step + 32'd1;
                if (sel_valid) begin
                    f <= f_new;
                    if (feas_next && f_new > best_f) begin
                        best_f    <= f_new;
                        best_step <= step + 32'd1;
                        best_x    <= x ^ onehot;
                    end
                end
            end
        end
    end
endmodule
// verilator lint_on WIDTHEXPAND
