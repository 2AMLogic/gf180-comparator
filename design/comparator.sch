v {xschem version=3.4.7 file_version=1.2
* comparator -- top sheet of the DR-0001 comparator block.
*
* This sheet exists so that `design/netlist.sh` has ONE cell to netlist and
* so that the whole hierarchy (comparator_dut -> comparator_dut_analog +
* comparator_dut_latch) is emitted into design/comparator.spice in one go.
* It carries no devices of its own: xschem emits a top-level cell as a
* COMMENTED `**.subckt` block, and design/netlist.sh deletes that block so
* the committed netlist is exactly the three contract subcircuits that
* sim/dut/README.md requires and nothing else.
}
G {}
K {}
V {}
S {}
E {}
C {devices/ipin.sym} -500 -400 0 0 {name=P1 lab=vinp}
C {devices/ipin.sym} -500 -340 0 0 {name=P2 lab=vinn}
C {devices/ipin.sym} -500 -280 0 0 {name=P3 lab=clk}
C {devices/ipin.sym} -500 -220 0 0 {name=P4 lab=ibias}
C {devices/opin.sym} -500 -160 0 0 {name=P5 lab=dout}
C {devices/opin.sym} -500 -100 0 0 {name=P6 lab=doutb}
C {devices/iopin.sym} -500 -40 0 0 {name=P7 lab=vdd}
C {devices/iopin.sym} -500 20 0 0 {name=P8 lab=vss}
C {comparator_dut.sym} 0 0 0 0 {name=DUT}
N -120 -90 -200 -90 {lab=vinp}
C {devices/lab_pin.sym} -200 -90 0 0 {name=DUT_vinp lab=vinp}
N -120 -30 -200 -30 {lab=vinn}
C {devices/lab_pin.sym} -200 -30 0 0 {name=DUT_vinn lab=vinn}
N -120 30 -200 30 {lab=clk}
C {devices/lab_pin.sym} -200 30 0 0 {name=DUT_clk lab=clk}
N -120 90 -200 90 {lab=ibias}
C {devices/lab_pin.sym} -200 90 0 0 {name=DUT_ibias lab=ibias}
N 120 -90 200 -90 {lab=dout}
C {devices/lab_pin.sym} 200 -90 0 0 {name=DUT_dout lab=dout}
N 120 -30 200 -30 {lab=doutb}
C {devices/lab_pin.sym} 200 -30 0 0 {name=DUT_doutb lab=doutb}
N 120 30 200 30 {lab=vdd}
C {devices/lab_pin.sym} 200 30 0 0 {name=DUT_vdd lab=vdd}
N 120 90 200 90 {lab=vss}
C {devices/lab_pin.sym} 200 90 0 0 {name=DUT_vss lab=vss}
