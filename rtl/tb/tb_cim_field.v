// Unit test of cim_field_unit against the golden CimField (3000 random vectors without noise and 3000 with the
// xorshift32 noise, N = 16, ADC resolution 2..16 bits changing from vector to vector).
// Plusargs: +vec0=<file> +vec1=<file> (written by scripts/golden/gen_cim_vectors.py).
module tb_cim_field;
    parameter N = 16;
    localparam LOG2N = $clog2(N);
    localparam HW = 18;

    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg                wr_p = 1'b0, ld_seed = 1'b0, ld = 1'b0;
    reg [LOG2N-1:0]    wr_row = 0, wr_col = 0;
    reg [7:0]          wr_val = 0;
    reg [31:0]         seed = 0;
    reg [15:0]         sg = 0;
    reg [4:0]          adc_bits = 5'd16;
    reg [N-1:0]        x = 0;
    reg [N*8-1:0]      d = 0;
    wire [N*HW-1:0]    h0, h1;

    cim_field_unit #(.N(N), .NOISE(0)) u0 (.clk(clk), .wr_p(wr_p), .wr_row(wr_row), .wr_col(wr_col), .wr_val(wr_val),
        .ld_seed(ld_seed), .seed(seed), .sg(sg), .adc_bits(adc_bits), .adc_fs(16'd0), .x(x), .d(d), .ld(ld), .h(h0));
    cim_field_unit #(.N(N), .NOISE(1)) u1 (.clk(clk), .wr_p(wr_p), .wr_row(wr_row), .wr_col(wr_col), .wr_val(wr_val),
        .ld_seed(ld_seed), .seed(seed), .sg(sg), .adc_bits(adc_bits), .adc_fs(16'd0), .x(x), .d(d), .ld(ld), .h(h1));

    integer errors = 0, checks = 0;
    reg [8*512-1:0] fname;
    integer fd, code, n_in, i, j, v, nv, bits, e, which;
    reg [31:0] sd, xv;
    reg [15:0] sgv;
    integer pm [0:N*N-1];
    integer dm [0:N-1];
    integer hv;

    task run_file(input integer w);
        begin
            if (w == 0) begin
                if (!$value$plusargs("vec0=%s", fname)) begin $display("FAIL tb_cim_field no +vec0"); $finish; end
            end else begin
                if (!$value$plusargs("vec1=%s", fname)) begin $display("FAIL tb_cim_field no +vec1"); $finish; end
            end
            fd = $fopen(fname, "r");
            if (fd == 0) begin $display("FAIL tb_cim_field cannot open vector file"); $finish; end
            code = $fscanf(fd, "%d %d %d", n_in, sd, v);
            sgv = v;
            for (i = 0; i < N * N; i = i + 1) code = $fscanf(fd, "%d", pm[i]);
            for (i = 0; i < N; i = i + 1) code = $fscanf(fd, "%d", dm[i]);
            code = $fscanf(fd, "%d", nv);
            // load the array (both units see the writes) and the biases
            for (i = 0; i < N; i = i + 1)
                for (j = 0; j < N; j = j + 1) begin
                    @(negedge clk);
                    wr_p = 1'b1; wr_row = i; wr_col = j; wr_val = pm[i * N + j];
                end
            @(negedge clk); wr_p = 1'b0;
            for (i = 0; i < N; i = i + 1) d[i*8 +: 8] = dm[i];
            seed = sd; sg = sgv;
            @(negedge clk); ld_seed = 1'b1;
            @(negedge clk); ld_seed = 1'b0;
            for (v = 0; v < nv; v = v + 1) begin
                code = $fscanf(fd, "%h %d", xv, bits);
                x = xv[N-1:0]; adc_bits = bits;
                @(negedge clk); ld = 1'b1;
                @(negedge clk); ld = 1'b0;
                for (i = 0; i < N; i = i + 1) begin
                    code = $fscanf(fd, "%d", hv);
                    if (w == 0) e = ($signed(h0[i*HW +: HW]) !== hv);
                    else        e = ($signed(h1[i*HW +: HW]) !== hv);
                    checks = checks + 1;
                    if (e) begin
                        errors = errors + 1;
                        if (errors < 10) $display("FAIL tb_cim_field file %0d vec %0d lane %0d bits %0d: rtl %0d golden %0d",
                                                  w, v, i, bits, (w == 0) ? $signed(h0[i*HW +: HW]) : $signed(h1[i*HW +: HW]), hv);
                    end
                end
            end
            $fclose(fd);
        end
    endtask

    initial begin
        run_file(0);
        // run_file(1) re-writes the array and re-seeds: the noise unit u1 is checked on file 1; u0 sees the same writes
        run_file(1);
        if (errors == 0) $display("PASS tb_cim_field 6000 random vectors, %0d field values equal golden (no noise and xorshift32 noise)", checks);
        else $display("FAIL tb_cim_field %0d mismatches", errors);
        $finish;
    end
endmodule
