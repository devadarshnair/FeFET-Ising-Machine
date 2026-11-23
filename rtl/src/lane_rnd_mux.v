// Tweak I5 lane groups: a lane of a group of 2^glog lanes takes the random word of the group leader (lane index with
// its low glog bits cleared). cand[g*32 +: 32] is the word of the leader for group size 2^g (g = 0: the lane's own).
// i5 = 0: the lane's own word. This models, in a digital simulation, "lanes share one device noise sample".
module lane_rnd_mux #(
    parameter LOG2N = 6
) (
    input  wire [32*(LOG2N+1)-1:0] cand,
    input  wire [3:0]              glog,
    input  wire                    i5,
    output wire [31:0]             rnd
);
    wire [3:0] gsel = (glog > LOG2N[3:0]) ? LOG2N[3:0] : glog;
    assign rnd = i5 ? cand[gsel*32 +: 32] : cand[31:0];
endmodule
