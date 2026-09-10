v {xschem version=3.4.7 file_version=1.2
* comparator_dut_latch -- DR-0001's decision stage.
*
*   XMTL/XM1..XM10  StrongARM latch, single clock phase, all four internal
*                   nodes precharged HIGH while clk is low. qp HIGH means
*                   inp > inn.
*   XIP1/XIN1,      two IDENTICAL isolation inverters, one per regeneration
*   XIP2/XIN2       node. They are load-bearing, not buffering for its own
*                   sake: an SR latch wired straight to the regeneration
*                   nodes loads them asymmetrically by its own held state
*                   (gf180-sar-adc DR-0015 measured ~10 mV of hysteresis
*                   doing exactly that). Both inverter inputs precharge to
*                   vdd and neither loading depends on the held answer.
*   XA*/XB*         cross-coupled NOR2 SR latch. sp = sn = 0 while clk is
*                   low, so the decision is HELD between strobes, which is
*                   what sim/dut/README.md's dout/doutb contract requires.
*
* Sizing rationale: spec/decision-records/DR-0001-comparator-topology.md.
}
G {}
K {}
V {}
S {}
E {}
C {devices/ipin.sym} -400 -900 0 0 {name=P1 lab=inp}
C {devices/ipin.sym} -400 -840 0 0 {name=P2 lab=inn}
C {devices/ipin.sym} -400 -780 0 0 {name=P3 lab=clk}
C {devices/opin.sym} -400 -720 0 0 {name=P4 lab=dout}
C {devices/opin.sym} -400 -660 0 0 {name=P5 lab=doutb}
C {devices/iopin.sym} -400 -600 0 0 {name=P6 lab=vdd}
C {devices/iopin.sym} -400 -540 0 0 {name=P7 lab=vss}
C {symbols/nfet_03v3.sym} 0 0 0 0 {name=MTL
L=0.5u
W=16u
nf=1
model=nfet_03v3
spiceprefix=X
}
N 20 -30 60 -30 {lab=ltail}
C {devices/lab_pin.sym} 60 -30 0 0 {name=MTL_d lab=ltail}
N -20 0 -60 0 {lab=clk}
C {devices/lab_pin.sym} -60 0 0 0 {name=MTL_g lab=clk}
N 20 30 60 30 {lab=vss}
C {devices/lab_pin.sym} 60 30 0 0 {name=MTL_s lab=vss}
N 20 0 40 0 {lab=vss}
C {devices/lab_pin.sym} 40 0 0 0 {name=MTL_b lab=vss}
C {symbols/nfet_03v3.sym} 240 -220 0 0 {name=M1
L=0.5u
W=8u
nf=1
model=nfet_03v3
spiceprefix=X
}
N 260 -250 300 -250 {lab=mn}
C {devices/lab_pin.sym} 300 -250 0 0 {name=M1_d lab=mn}
N 220 -220 180 -220 {lab=inp}
C {devices/lab_pin.sym} 180 -220 0 0 {name=M1_g lab=inp}
N 260 -190 300 -190 {lab=ltail}
C {devices/lab_pin.sym} 300 -190 0 0 {name=M1_s lab=ltail}
N 260 -220 280 -220 {lab=vss}
C {devices/lab_pin.sym} 280 -220 0 0 {name=M1_b lab=vss}
C {symbols/nfet_03v3.sym} 520 -220 0 0 {name=M2
L=0.5u
W=8u
nf=1
model=nfet_03v3
spiceprefix=X
}
N 540 -250 580 -250 {lab=mp}
C {devices/lab_pin.sym} 580 -250 0 0 {name=M2_d lab=mp}
N 500 -220 460 -220 {lab=inn}
C {devices/lab_pin.sym} 460 -220 0 0 {name=M2_g lab=inn}
N 540 -190 580 -190 {lab=ltail}
C {devices/lab_pin.sym} 580 -190 0 0 {name=M2_s lab=ltail}
N 540 -220 560 -220 {lab=vss}
C {devices/lab_pin.sym} 560 -220 0 0 {name=M2_b lab=vss}
C {symbols/nfet_03v3.sym} 240 -440 0 0 {name=M3
L=0.5u
W=6u
nf=1
model=nfet_03v3
spiceprefix=X
}
N 260 -470 300 -470 {lab=qn}
C {devices/lab_pin.sym} 300 -470 0 0 {name=M3_d lab=qn}
N 220 -440 180 -440 {lab=qp}
C {devices/lab_pin.sym} 180 -440 0 0 {name=M3_g lab=qp}
N 260 -410 300 -410 {lab=mn}
C {devices/lab_pin.sym} 300 -410 0 0 {name=M3_s lab=mn}
N 260 -440 280 -440 {lab=vss}
C {devices/lab_pin.sym} 280 -440 0 0 {name=M3_b lab=vss}
C {symbols/nfet_03v3.sym} 520 -440 0 0 {name=M4
L=0.5u
W=6u
nf=1
model=nfet_03v3
spiceprefix=X
}
N 540 -470 580 -470 {lab=qp}
C {devices/lab_pin.sym} 580 -470 0 0 {name=M4_d lab=qp}
N 500 -440 460 -440 {lab=qn}
C {devices/lab_pin.sym} 460 -440 0 0 {name=M4_g lab=qn}
N 540 -410 580 -410 {lab=mp}
C {devices/lab_pin.sym} 580 -410 0 0 {name=M4_s lab=mp}
N 540 -440 560 -440 {lab=vss}
C {devices/lab_pin.sym} 560 -440 0 0 {name=M4_b lab=vss}
C {symbols/pfet_03v3.sym} 240 -660 0 0 {name=M5
L=0.5u
W=6u
nf=1
model=pfet_03v3
spiceprefix=X
}
N 260 -630 300 -630 {lab=qn}
C {devices/lab_pin.sym} 300 -630 0 0 {name=M5_d lab=qn}
N 220 -660 180 -660 {lab=qp}
C {devices/lab_pin.sym} 180 -660 0 0 {name=M5_g lab=qp}
N 260 -690 300 -690 {lab=vdd}
C {devices/lab_pin.sym} 300 -690 0 0 {name=M5_s lab=vdd}
N 260 -660 280 -660 {lab=vdd}
C {devices/lab_pin.sym} 280 -660 0 0 {name=M5_b lab=vdd}
C {symbols/pfet_03v3.sym} 520 -660 0 0 {name=M6
L=0.5u
W=6u
nf=1
model=pfet_03v3
spiceprefix=X
}
N 540 -630 580 -630 {lab=qp}
C {devices/lab_pin.sym} 580 -630 0 0 {name=M6_d lab=qp}
N 500 -660 460 -660 {lab=qn}
C {devices/lab_pin.sym} 460 -660 0 0 {name=M6_g lab=qn}
N 540 -690 580 -690 {lab=vdd}
C {devices/lab_pin.sym} 580 -690 0 0 {name=M6_s lab=vdd}
N 540 -660 560 -660 {lab=vdd}
C {devices/lab_pin.sym} 560 -660 0 0 {name=M6_b lab=vdd}
C {symbols/pfet_03v3.sym} 800 -660 0 0 {name=M7
L=0.5u
W=4u
nf=1
model=pfet_03v3
spiceprefix=X
}
N 820 -630 860 -630 {lab=qn}
C {devices/lab_pin.sym} 860 -630 0 0 {name=M7_d lab=qn}
N 780 -660 740 -660 {lab=clk}
C {devices/lab_pin.sym} 740 -660 0 0 {name=M7_g lab=clk}
N 820 -690 860 -690 {lab=vdd}
C {devices/lab_pin.sym} 860 -690 0 0 {name=M7_s lab=vdd}
N 820 -660 840 -660 {lab=vdd}
C {devices/lab_pin.sym} 840 -660 0 0 {name=M7_b lab=vdd}
C {symbols/pfet_03v3.sym} 1080 -660 0 0 {name=M8
L=0.5u
W=4u
nf=1
model=pfet_03v3
spiceprefix=X
}
N 1100 -630 1140 -630 {lab=qp}
C {devices/lab_pin.sym} 1140 -630 0 0 {name=M8_d lab=qp}
N 1060 -660 1020 -660 {lab=clk}
C {devices/lab_pin.sym} 1020 -660 0 0 {name=M8_g lab=clk}
N 1100 -690 1140 -690 {lab=vdd}
C {devices/lab_pin.sym} 1140 -690 0 0 {name=M8_s lab=vdd}
N 1100 -660 1120 -660 {lab=vdd}
C {devices/lab_pin.sym} 1120 -660 0 0 {name=M8_b lab=vdd}
C {symbols/pfet_03v3.sym} 800 -440 0 0 {name=M9
L=0.5u
W=2u
nf=1
model=pfet_03v3
spiceprefix=X
}
N 820 -410 860 -410 {lab=mn}
C {devices/lab_pin.sym} 860 -410 0 0 {name=M9_d lab=mn}
N 780 -440 740 -440 {lab=clk}
C {devices/lab_pin.sym} 740 -440 0 0 {name=M9_g lab=clk}
N 820 -470 860 -470 {lab=vdd}
C {devices/lab_pin.sym} 860 -470 0 0 {name=M9_s lab=vdd}
N 820 -440 840 -440 {lab=vdd}
C {devices/lab_pin.sym} 840 -440 0 0 {name=M9_b lab=vdd}
C {symbols/pfet_03v3.sym} 1080 -440 0 0 {name=M10
L=0.5u
W=2u
nf=1
model=pfet_03v3
spiceprefix=X
}
N 1100 -410 1140 -410 {lab=mp}
C {devices/lab_pin.sym} 1140 -410 0 0 {name=M10_d lab=mp}
N 1060 -440 1020 -440 {lab=clk}
C {devices/lab_pin.sym} 1020 -440 0 0 {name=M10_g lab=clk}
N 1100 -470 1140 -470 {lab=vdd}
C {devices/lab_pin.sym} 1140 -470 0 0 {name=M10_s lab=vdd}
N 1100 -440 1120 -440 {lab=vdd}
C {devices/lab_pin.sym} 1120 -440 0 0 {name=M10_b lab=vdd}
C {symbols/pfet_03v3.sym} 800 -220 0 0 {name=IP1
L=0.5u
W=5u
nf=1
model=pfet_03v3
spiceprefix=X
}
N 820 -190 860 -190 {lab=sp}
C {devices/lab_pin.sym} 860 -190 0 0 {name=IP1_d lab=sp}
N 780 -220 740 -220 {lab=qp}
C {devices/lab_pin.sym} 740 -220 0 0 {name=IP1_g lab=qp}
N 820 -250 860 -250 {lab=vdd}
C {devices/lab_pin.sym} 860 -250 0 0 {name=IP1_s lab=vdd}
N 820 -220 840 -220 {lab=vdd}
C {devices/lab_pin.sym} 840 -220 0 0 {name=IP1_b lab=vdd}
C {symbols/nfet_03v3.sym} 800 0 0 0 {name=IN1
L=0.5u
W=2u
nf=1
model=nfet_03v3
spiceprefix=X
}
N 820 -30 860 -30 {lab=sp}
C {devices/lab_pin.sym} 860 -30 0 0 {name=IN1_d lab=sp}
N 780 0 740 0 {lab=qp}
C {devices/lab_pin.sym} 740 0 0 0 {name=IN1_g lab=qp}
N 820 30 860 30 {lab=vss}
C {devices/lab_pin.sym} 860 30 0 0 {name=IN1_s lab=vss}
N 820 0 840 0 {lab=vss}
C {devices/lab_pin.sym} 840 0 0 0 {name=IN1_b lab=vss}
C {symbols/pfet_03v3.sym} 1080 -220 0 0 {name=IP2
L=0.5u
W=5u
nf=1
model=pfet_03v3
spiceprefix=X
}
N 1100 -190 1140 -190 {lab=sn}
C {devices/lab_pin.sym} 1140 -190 0 0 {name=IP2_d lab=sn}
N 1060 -220 1020 -220 {lab=qn}
C {devices/lab_pin.sym} 1020 -220 0 0 {name=IP2_g lab=qn}
N 1100 -250 1140 -250 {lab=vdd}
C {devices/lab_pin.sym} 1140 -250 0 0 {name=IP2_s lab=vdd}
N 1100 -220 1120 -220 {lab=vdd}
C {devices/lab_pin.sym} 1120 -220 0 0 {name=IP2_b lab=vdd}
C {symbols/nfet_03v3.sym} 1080 0 0 0 {name=IN2
L=0.5u
W=2u
nf=1
model=nfet_03v3
spiceprefix=X
}
N 1100 -30 1140 -30 {lab=sn}
C {devices/lab_pin.sym} 1140 -30 0 0 {name=IN2_d lab=sn}
N 1060 0 1020 0 {lab=qn}
C {devices/lab_pin.sym} 1020 0 0 0 {name=IN2_g lab=qn}
N 1100 30 1140 30 {lab=vss}
C {devices/lab_pin.sym} 1140 30 0 0 {name=IN2_s lab=vss}
N 1100 0 1120 0 {lab=vss}
C {devices/lab_pin.sym} 1120 0 0 0 {name=IN2_b lab=vss}
C {symbols/pfet_03v3.sym} 1360 -660 0 0 {name=A1P
L=0.5u
W=10u
nf=1
model=pfet_03v3
spiceprefix=X
}
N 1380 -630 1420 -630 {lab=na}
C {devices/lab_pin.sym} 1420 -630 0 0 {name=A1P_d lab=na}
N 1340 -660 1300 -660 {lab=sp}
C {devices/lab_pin.sym} 1300 -660 0 0 {name=A1P_g lab=sp}
N 1380 -690 1420 -690 {lab=vdd}
C {devices/lab_pin.sym} 1420 -690 0 0 {name=A1P_s lab=vdd}
N 1380 -660 1400 -660 {lab=vdd}
C {devices/lab_pin.sym} 1400 -660 0 0 {name=A1P_b lab=vdd}
C {symbols/pfet_03v3.sym} 1360 -440 0 0 {name=A2P
L=0.5u
W=10u
nf=1
model=pfet_03v3
spiceprefix=X
}
N 1380 -410 1420 -410 {lab=dout}
C {devices/lab_pin.sym} 1420 -410 0 0 {name=A2P_d lab=dout}
N 1340 -440 1300 -440 {lab=doutb}
C {devices/lab_pin.sym} 1300 -440 0 0 {name=A2P_g lab=doutb}
N 1380 -470 1420 -470 {lab=na}
C {devices/lab_pin.sym} 1420 -470 0 0 {name=A2P_s lab=na}
N 1380 -440 1400 -440 {lab=vdd}
C {devices/lab_pin.sym} 1400 -440 0 0 {name=A2P_b lab=vdd}
C {symbols/nfet_03v3.sym} 1360 -220 0 0 {name=A1N
L=0.5u
W=2u
nf=1
model=nfet_03v3
spiceprefix=X
}
N 1380 -250 1420 -250 {lab=dout}
C {devices/lab_pin.sym} 1420 -250 0 0 {name=A1N_d lab=dout}
N 1340 -220 1300 -220 {lab=sp}
C {devices/lab_pin.sym} 1300 -220 0 0 {name=A1N_g lab=sp}
N 1380 -190 1420 -190 {lab=vss}
C {devices/lab_pin.sym} 1420 -190 0 0 {name=A1N_s lab=vss}
N 1380 -220 1400 -220 {lab=vss}
C {devices/lab_pin.sym} 1400 -220 0 0 {name=A1N_b lab=vss}
C {symbols/nfet_03v3.sym} 1360 0 0 0 {name=A2N
L=0.5u
W=2u
nf=1
model=nfet_03v3
spiceprefix=X
}
N 1380 -30 1420 -30 {lab=dout}
C {devices/lab_pin.sym} 1420 -30 0 0 {name=A2N_d lab=dout}
N 1340 0 1300 0 {lab=doutb}
C {devices/lab_pin.sym} 1300 0 0 0 {name=A2N_g lab=doutb}
N 1380 30 1420 30 {lab=vss}
C {devices/lab_pin.sym} 1420 30 0 0 {name=A2N_s lab=vss}
N 1380 0 1400 0 {lab=vss}
C {devices/lab_pin.sym} 1400 0 0 0 {name=A2N_b lab=vss}
C {symbols/pfet_03v3.sym} 1640 -660 0 0 {name=B1P
L=0.5u
W=10u
nf=1
model=pfet_03v3
spiceprefix=X
}
N 1660 -630 1700 -630 {lab=nb}
C {devices/lab_pin.sym} 1700 -630 0 0 {name=B1P_d lab=nb}
N 1620 -660 1580 -660 {lab=sn}
C {devices/lab_pin.sym} 1580 -660 0 0 {name=B1P_g lab=sn}
N 1660 -690 1700 -690 {lab=vdd}
C {devices/lab_pin.sym} 1700 -690 0 0 {name=B1P_s lab=vdd}
N 1660 -660 1680 -660 {lab=vdd}
C {devices/lab_pin.sym} 1680 -660 0 0 {name=B1P_b lab=vdd}
C {symbols/pfet_03v3.sym} 1640 -440 0 0 {name=B2P
L=0.5u
W=10u
nf=1
model=pfet_03v3
spiceprefix=X
}
N 1660 -410 1700 -410 {lab=doutb}
C {devices/lab_pin.sym} 1700 -410 0 0 {name=B2P_d lab=doutb}
N 1620 -440 1580 -440 {lab=dout}
C {devices/lab_pin.sym} 1580 -440 0 0 {name=B2P_g lab=dout}
N 1660 -470 1700 -470 {lab=nb}
C {devices/lab_pin.sym} 1700 -470 0 0 {name=B2P_s lab=nb}
N 1660 -440 1680 -440 {lab=vdd}
C {devices/lab_pin.sym} 1680 -440 0 0 {name=B2P_b lab=vdd}
C {symbols/nfet_03v3.sym} 1640 -220 0 0 {name=B1N
L=0.5u
W=2u
nf=1
model=nfet_03v3
spiceprefix=X
}
N 1660 -250 1700 -250 {lab=doutb}
C {devices/lab_pin.sym} 1700 -250 0 0 {name=B1N_d lab=doutb}
N 1620 -220 1580 -220 {lab=sn}
C {devices/lab_pin.sym} 1580 -220 0 0 {name=B1N_g lab=sn}
N 1660 -190 1700 -190 {lab=vss}
C {devices/lab_pin.sym} 1700 -190 0 0 {name=B1N_s lab=vss}
N 1660 -220 1680 -220 {lab=vss}
C {devices/lab_pin.sym} 1680 -220 0 0 {name=B1N_b lab=vss}
C {symbols/nfet_03v3.sym} 1640 0 0 0 {name=B2N
L=0.5u
W=2u
nf=1
model=nfet_03v3
spiceprefix=X
}
N 1660 -30 1700 -30 {lab=doutb}
C {devices/lab_pin.sym} 1700 -30 0 0 {name=B2N_d lab=doutb}
N 1620 0 1580 0 {lab=dout}
C {devices/lab_pin.sym} 1580 0 0 0 {name=B2N_g lab=dout}
N 1660 30 1700 30 {lab=vss}
C {devices/lab_pin.sym} 1700 30 0 0 {name=B2N_s lab=vss}
N 1660 0 1680 0 {lab=vss}
C {devices/lab_pin.sym} 1680 0 0 0 {name=B2N_b lab=vss}
