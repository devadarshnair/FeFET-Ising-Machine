// Unit test: constraint unit (W memory, capacities, loads, slacks, feas_next) at N = 16, NCON = 8.
// Random flips; after each, loads must equal W x and slacks C - W x; feas_next (computed before the flip) must say
// whether the new state is feasible. With en = 0 (QUBO mode) loads must not move and feas_next must be 1.
module tb_constraint;
    localparam N = 16, NCON = 8, LDW = 16;

    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg              wr_w = 1'b0, wr_c = 1'b0, clr = 1'b0, rd_en = 1'b0, upd = 1'b0, dir = 1'b0, en = 1'b1;
    reg [3:0]        wr_con = 4'd0, wr_item = 4'd0, rd_item = 4'd0;
    reg [15:0]       wr_data = 16'd0;
    wire [NCON*LDW-1:0]     load;
    wire [NCON*(LDW+1)-1:0] slack;
    wire                    feas_next;

    constraint_unit #(.N(N), .NCON(NCON), .WW(6), .LDW(LDW)) dut (
        .clk(clk), .wr_w(wr_w), .wr_c(wr_c), .wr_con(wr_con), .wr_item(wr_item), .wr_data(wr_data), .clr(clr),
        .rd_en(rd_en), .rd_item(rd_item), .upd(upd), .dir(dir), .en(en), .load(load), .slack(slack),
        .feas_next(feas_next));

    integer w [0:NCON-1][0:N-1];
    integer c [0:NCON-1];
    integer xs [0:N-1];
    integer seed, i, j, t, k, errors, lv, feas, n_feas, n_infeas;
    reg got_feas;

    task check_loads;
        integer jj, ii, l;
        begin
            for (jj = 0; jj < NCON; jj = jj + 1) begin
                l = 0;
                for (ii = 0; ii < N; ii = ii + 1) l = l + w[jj][ii] * xs[ii];   // xs is frozen when en = 0
                if (load[jj*LDW +: LDW] != l || $signed(slack[jj*(LDW+1) +: LDW+1]) != c[jj] - l) begin
                    errors = errors + 1;
                    if (errors < 10) $display("tb_constraint: con %0d load %0d want %0d", jj, load[jj*LDW +: LDW], l);
                end
            end
        end
    endtask

    initial begin
        errors = 0; seed = 8; n_feas = 0; n_infeas = 0;
        for (j = 0; j < NCON; j = j + 1) begin
            lv = 0;
            for (i = 0; i < N; i = i + 1) begin
                w[j][i] = 1 + {$random(seed)} % 50;
                lv = lv + w[j][i];
                @(negedge clk) begin wr_w = 1'b1; wr_con = j; wr_item = i; wr_data = w[j][i]; end
            end
            c[j] = lv / 3;
            @(negedge clk) begin wr_w = 1'b0; wr_c = 1'b1; wr_con = j; wr_data = c[j]; end
            @(negedge clk) wr_c = 1'b0;
        end
        for (i = 0; i < N; i = i + 1) xs[i] = 0;
        @(negedge clk) clr = 1'b1;
        @(negedge clk) clr = 1'b0;
        for (t = 0; t < 3000; t = t + 1) begin
            if (t == 2500) en = 1'b0;
            k = {$random(seed)} % N;
            @(negedge clk) begin rd_en = 1'b1; rd_item = k; end
            @(negedge clk) begin rd_en = 1'b0; dir = (xs[k] == 0); end
            #1 got_feas = feas_next;
            @(negedge clk) upd = 1'b1;
            @(negedge clk) upd = 1'b0;
            if (en) xs[k] = 1 - xs[k];
            feas = 1;
            for (j = 0; j < NCON; j = j + 1) begin
                lv = 0;
                for (i = 0; i < N; i = i + 1) lv = lv + w[j][i] * xs[i];
                if (lv > c[j]) feas = 0;
            end
            if (!en) feas = 1;
            if (feas) n_feas = n_feas + 1; else n_infeas = n_infeas + 1;
            if (got_feas !== feas) begin
                errors = errors + 1;
                if (errors < 10) $display("tb_constraint: step %0d feas_next %b want %0d", t, got_feas, feas);
            end
            check_loads;
        end
        if (n_feas < 100 || n_infeas < 100) begin
            errors = errors + 1;
            $display("tb_constraint: weak test, %0d feasible and %0d infeasible states", n_feas, n_infeas);
        end
        if (errors == 0)
            $display("PASS tb_constraint (3000 flips, %0d feasible / %0d infeasible after-flip states; en = 0 holds)",
                     n_feas, n_infeas);
        else
            $display("FAIL tb_constraint: %0d errors", errors);
        $finish;
    end
endmodule
