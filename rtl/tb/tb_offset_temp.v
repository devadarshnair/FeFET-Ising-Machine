// Unit test: offset unit (reset on accept, grow by deoff, saturate at 2^24 - 1) and temperature register
// (T = (T * alpha) >> 32 per step when geom = 1, hold when geom = 0), against references in the testbench.
module tb_offset_temp;
    reg clk = 1'b0;
    always #5 clk = ~clk;

    reg         clr = 1'b0, upd = 1'b0, accepted = 1'b0, load = 1'b0, step = 1'b0, geom = 1'b0;
    reg  [15:0] deoff = 16'd0;
    reg  [31:0] t0 = 32'd0, alpha = 32'd0;
    wire [23:0] eoff;
    wire [31:0] temp;

    offset_unit #(.EW(24)) u_off (.clk(clk), .clr(clr), .upd(upd), .accepted(accepted), .deoff(deoff), .eoff(eoff));
    temp_sched u_t (.clk(clk), .load(load), .t0(t0), .step(step), .geom(geom), .alpha(alpha), .temp(temp));

    integer seed, k, errors, n_sat;
    reg [63:0] want_e, want_t;

    initial begin
        errors = 0; seed = 31; n_sat = 0;
        @(negedge clk) clr = 1'b1;
        @(negedge clk) clr = 1'b0;
        want_e = 0;
        for (k = 0; k < 5000; k = k + 1) begin
            deoff    = (k < 2500) ? ($random(seed) & 16'h00FF) : 16'hFFFF;
            accepted = (k < 2500) ? (($random(seed) & 3) == 0) : (($random(seed) & 255) == 0);
            @(negedge clk) upd = 1'b1;
            @(negedge clk) upd = 1'b0;
            want_e = accepted ? 0 : ((want_e + deoff > 64'hFFFFFF) ? 64'hFFFFFF : want_e + deoff);
            if (want_e == 64'hFFFFFF) n_sat = n_sat + 1;
            if (eoff !== want_e[23:0]) begin
                errors = errors + 1;
                if (errors < 10) $display("tb_offset_temp: eoff %0d want %0d", eoff, want_e);
            end
        end
        if (n_sat == 0) begin errors = errors + 1; $display("tb_offset_temp: saturation never reached"); end

        for (k = 0; k < 3; k = k + 1) begin
            t0    = (k == 0) ? 32'hFFFFFFFF : $random(seed);
            alpha = (k == 2) ? 32'hFFFFFFFF : ($random(seed) | 32'hF0000000);
            @(negedge clk) load = 1'b1;
            @(negedge clk) begin load = 1'b0; geom = 1'b1; end
            want_t = t0;
            repeat (2000) begin
                @(negedge clk) step = 1'b1;
                @(negedge clk) step = 1'b0;
                want_t = (want_t * alpha) >> 32;
                if (temp !== want_t[31:0]) begin
                    errors = errors + 1;
                    if (errors < 10) $display("tb_offset_temp: T %0d want %0d", temp, want_t);
                end
            end
            geom = 1'b0;
            repeat (10) begin
                @(negedge clk) step = 1'b1;
                @(negedge clk) step = 1'b0;
            end
            if (temp !== want_t[31:0]) begin errors = errors + 1; $display("tb_offset_temp: T did not hold"); end
        end
        if (errors == 0)
            $display("PASS tb_offset_temp (5000 offset updates, %0d saturated; 3 x 2000 schedule steps; hold)", n_sat);
        else
            $display("FAIL tb_offset_temp: %0d errors", errors);
        $finish;
    end
endmodule
