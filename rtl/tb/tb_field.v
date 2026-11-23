// Unit test: the local-field array (N field_units fed by N coupling_mem rows), incremental update against a full
// recompute h = d + P x after every one of many random flips. Also checks that the overflow flag stays low, and
// that it rises when a field is pushed past the 18-bit range.
module tb_field;
    localparam N = 16, HW = 18;

    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg        wr_p = 1'b0, wr_b = 1'b0, rd_en = 1'b0, init = 1'b0, upd = 1'b0, dir = 1'b0;
    reg [3:0]  wr_row = 4'd0, wr_col = 4'd0, rd_col = 4'd0;
    reg [7:0]  wr_data = 8'd0;
    wire [N*HW-1:0] h;
    wire [N-1:0]    ovf;

    genvar j;
    generate
        for (j = 0; j < N; j = j + 1) begin : lane
            wire [7:0] pk, bias;
            coupling_mem #(.N(N)) u_c (.clk(clk), .wr_p(wr_p && wr_row == j), .wr_b(wr_b && wr_row == j),
                                       .wr_col(wr_col), .wr_data(wr_data), .rd_en(rd_en), .rd_col(rd_col),
                                       .pk(pk), .bias(bias));
            field_unit #(.HW(HW)) u_f (.clk(clk), .init(init), .bias(bias), .upd(upd), .dir(dir), .pk(pk),
                                       .h(h[j*HW +: HW]), .ovf(ovf[j]));
        end
    endgenerate

    integer P [0:N-1][0:N-1];
    integer d [0:N-1];
    integer xs [0:N-1];
    integer seed, a, b, k, t, errors, want, phase;

    task write_p(input integer row, input integer col, input integer val);
        begin
            @(negedge clk) begin wr_p = 1'b1; wr_row = row; wr_col = col; wr_data = val; end
            @(negedge clk) wr_p = 1'b0;
        end
    endtask

    task flip(input integer kk);
        begin
            @(negedge clk) begin rd_en = 1'b1; rd_col = kk; end
            @(negedge clk) begin rd_en = 1'b0; upd = 1'b1; dir = (xs[kk] == 0); end
            @(negedge clk) upd = 1'b0;
            xs[kk] = 1 - xs[kk];
        end
    endtask

    task compare;
        integer i, q, hv;
        begin
            for (i = 0; i < N; i = i + 1) begin
                hv = d[i];
                for (q = 0; q < N; q = q + 1) hv = hv + P[i][q] * xs[q];
                if ($signed(h[i*HW +: HW]) != hv) begin
                    errors = errors + 1;
                    if (errors < 10) $display("tb_field: lane %0d h=%0d want %0d", i, $signed(h[i*HW +: HW]), hv);
                end
            end
        end
    endtask

    initial begin
        errors = 0; seed = 99;
        for (a = 0; a < N; a = a + 1) begin
            d[a] = ($random(seed) % 128);
            xs[a] = 0;
            P[a][a] = 0;
            for (b = a + 1; b < N; b = b + 1) begin
                P[a][b] = $random(seed) % 128;
                P[b][a] = P[a][b];
            end
        end
        for (a = 0; a < N; a = a + 1) begin
            @(negedge clk) begin wr_b = 1'b1; wr_row = a; wr_data = d[a]; end
            @(negedge clk) wr_b = 1'b0;
            for (b = 0; b < N; b = b + 1) write_p(a, b, P[a][b]);
        end
        @(negedge clk) init = 1'b1;
        @(negedge clk) init = 1'b0;
        compare;
        for (t = 0; t < 3000; t = t + 1) begin
            k = {$random(seed)} % N;
            flip(k);
            compare;
        end
        if (ovf != 0) begin
            errors = errors + 1;
            $display("tb_field: ovf set in normal use");
        end
        // overflow: lane 0 gets +127 from every other lane, flipped in and out with dir forced to 1
        for (b = 1; b < N; b = b + 1) write_p(0, b, 127);
        for (t = 0; t < 1100; t = t + 1) begin
            @(negedge clk) begin rd_en = 1'b1; rd_col = 1; end
            @(negedge clk) begin rd_en = 1'b0; upd = 1'b1; dir = 1'b1; end
            @(negedge clk) upd = 1'b0;
        end
        if (ovf[0] !== 1'b1) begin
            errors = errors + 1;
            $display("tb_field: ovf did not rise after 1100 x 127 added to lane 0");
        end
        if (errors == 0)
            $display("PASS tb_field (3000 random flips at N=%0d, every field equal to d + P x; overflow flag works)", N);
        else
            $display("FAIL tb_field: %0d mismatches", errors);
        $finish;
    end
endmodule
