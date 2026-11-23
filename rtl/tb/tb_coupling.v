// Unit test: coupling memory of one lane (N = 64 words). Every word and the bias are written with random values,
// then read back in random order; the read is registered (data one cycle after rd_en) and holds without rd_en.
module tb_coupling;
    localparam N = 64;

    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg        wr_p = 1'b0, wr_b = 1'b0, rd_en = 1'b0;
    reg [5:0]  wr_col = 6'd0, rd_col = 6'd0;
    reg [7:0]  wr_data = 8'd0;
    wire [7:0] pk, bias;

    coupling_mem #(.N(N)) dut (.clk(clk), .wr_p(wr_p), .wr_b(wr_b), .wr_col(wr_col), .wr_data(wr_data),
                               .rd_en(rd_en), .rd_col(rd_col), .pk(pk), .bias(bias));

    reg [7:0] shadow [0:N-1];
    integer seed, k, t, errors;

    initial begin
        errors = 0; seed = 5;
        for (k = 0; k < N; k = k + 1) begin
            shadow[k] = $random(seed);
            @(negedge clk) begin wr_p = 1'b1; wr_col = k; wr_data = shadow[k]; end
        end
        @(negedge clk) begin wr_p = 1'b0; wr_b = 1'b1; wr_data = 8'h9C; end
        @(negedge clk) wr_b = 1'b0;
        if (bias !== 8'h9C) begin errors = errors + 1; $display("tb_coupling: bias %h", bias); end
        for (t = 0; t < 500; t = t + 1) begin
            k = {$random(seed)} % N;
            @(negedge clk) begin rd_en = 1'b1; rd_col = k; end
            @(negedge clk) begin rd_en = 1'b0; rd_col = k + 1; end
            if (pk !== shadow[k]) begin
                errors = errors + 1;
                if (errors < 10) $display("tb_coupling: word %0d read %h want %h", k, pk, shadow[k]);
            end
            @(negedge clk);
            if (pk !== shadow[k]) begin
                errors = errors + 1;
                if (errors < 10) $display("tb_coupling: word %0d did not hold", k);
            end
        end
        if (errors == 0)
            $display("PASS tb_coupling (%0d words written, 500 random reads)", N);
        else
            $display("FAIL tb_coupling: %0d errors", errors);
        $finish;
    end
endmodule
