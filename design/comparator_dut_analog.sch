v {xschem version=3.4.7 file_version=1.2
* comparator_dut_analog -- the DC-resolvable front end of DR-0001's comparator.
*
* Static NMOS-input differential preamplifier: 30/2 um input pair at
* gm/ID = 15 1/V (Vov ~ 50 mV), 1:2 NMOS tail mirror off the `ibias` pin,
* 1 um x 120 um unsalicided p+ poly loads (ppolyf_u_1k, ~124 kohm).
* Sizing derivation and the gm/ID rows it is cited against:
* spec/decision-records/DR-0001-comparator-topology.md.
*
* This cell exists as its own subcircuit because sim/comparator-offset-mc/
* and sim/comparator-preamp-noise/ are small-signal analyses about a DC
* operating point -- see sim/dut/README.md 'Why the DUT is split into three
* subckts'.
}
G {}
K {}
V {}
S {}
E {}
C {devices/ipin.sym} -400 -600 0 0 {name=P1 lab=vinp}
C {devices/ipin.sym} -400 -540 0 0 {name=P2 lab=vinn}
C {devices/ipin.sym} -400 -480 0 0 {name=P3 lab=ibias}
C {devices/opin.sym} -400 -420 0 0 {name=P4 lab=aop}
C {devices/opin.sym} -400 -360 0 0 {name=P5 lab=aon}
C {devices/iopin.sym} -400 -300 0 0 {name=P6 lab=vdd}
C {devices/iopin.sym} -400 -240 0 0 {name=P7 lab=vss}
C {symbols/nfet_03v3.sym} 0 0 0 0 {name=MB
L=4u
W=5u
nf=1
model=nfet_03v3
spiceprefix=X
}
N 20 -30 60 -30 {lab=ibias}
C {devices/lab_pin.sym} 60 -30 0 0 {name=MB_d lab=ibias}
N -20 0 -60 0 {lab=ibias}
C {devices/lab_pin.sym} -60 0 0 0 {name=MB_g lab=ibias}
N 20 30 60 30 {lab=vss}
C {devices/lab_pin.sym} 60 30 0 0 {name=MB_s lab=vss}
N 20 0 40 0 {lab=vss}
C {devices/lab_pin.sym} 40 0 0 0 {name=MB_b lab=vss}
C {symbols/nfet_03v3.sym} 240 0 0 0 {name=MT
L=4u
W=10u
nf=1
model=nfet_03v3
spiceprefix=X
}
N 260 -30 300 -30 {lab=atail}
C {devices/lab_pin.sym} 300 -30 0 0 {name=MT_d lab=atail}
N 220 0 180 0 {lab=ibias}
C {devices/lab_pin.sym} 180 0 0 0 {name=MT_g lab=ibias}
N 260 30 300 30 {lab=vss}
C {devices/lab_pin.sym} 300 30 0 0 {name=MT_s lab=vss}
N 260 0 280 0 {lab=vss}
C {devices/lab_pin.sym} 280 0 0 0 {name=MT_b lab=vss}
C {symbols/nfet_03v3.sym} 240 -240 0 0 {name=MIP
L=2u
W=30u
nf=1
model=nfet_03v3
spiceprefix=X
}
N 260 -270 300 -270 {lab=aon}
C {devices/lab_pin.sym} 300 -270 0 0 {name=MIP_d lab=aon}
N 220 -240 180 -240 {lab=vinp}
C {devices/lab_pin.sym} 180 -240 0 0 {name=MIP_g lab=vinp}
N 260 -210 300 -210 {lab=atail}
C {devices/lab_pin.sym} 300 -210 0 0 {name=MIP_s lab=atail}
N 260 -240 280 -240 {lab=vss}
C {devices/lab_pin.sym} 280 -240 0 0 {name=MIP_b lab=vss}
C {symbols/nfet_03v3.sym} 520 -240 0 0 {name=MIN
L=2u
W=30u
nf=1
model=nfet_03v3
spiceprefix=X
}
N 540 -270 580 -270 {lab=aop}
C {devices/lab_pin.sym} 580 -270 0 0 {name=MIN_d lab=aop}
N 500 -240 460 -240 {lab=vinn}
C {devices/lab_pin.sym} 460 -240 0 0 {name=MIN_g lab=vinn}
N 540 -210 580 -210 {lab=atail}
C {devices/lab_pin.sym} 580 -210 0 0 {name=MIN_s lab=atail}
N 540 -240 560 -240 {lab=vss}
C {devices/lab_pin.sym} 560 -240 0 0 {name=MIN_b lab=vss}
C {symbols/ppolyf_u_1k.sym} 240 -460 0 0 {name=RN
W=1u
L=120u
model=ppolyf_u_1k
spiceprefix=X
m=1
}
N 240 -430 240 -390 {lab=aon}
C {devices/lab_pin.sym} 240 -390 0 0 {name=RN_m lab=aon}
N 240 -490 240 -530 {lab=vdd}
C {devices/lab_pin.sym} 240 -530 0 0 {name=RN_p lab=vdd}
N 220 -460 180 -460 {lab=vss}
C {devices/lab_pin.sym} 180 -460 0 0 {name=RN_b lab=vss}
C {symbols/ppolyf_u_1k.sym} 520 -460 0 0 {name=RP
W=1u
L=120u
model=ppolyf_u_1k
spiceprefix=X
m=1
}
N 520 -430 520 -390 {lab=aop}
C {devices/lab_pin.sym} 520 -390 0 0 {name=RP_m lab=aop}
N 520 -490 520 -530 {lab=vdd}
C {devices/lab_pin.sym} 520 -530 0 0 {name=RP_p lab=vdd}
N 500 -460 460 -460 {lab=vss}
C {devices/lab_pin.sym} 460 -460 0 0 {name=RP_b lab=vss}
