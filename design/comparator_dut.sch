v {xschem version=3.4.7 file_version=1.2
* comparator_dut -- DR-0001's full clocked comparator.
*
* Static preamplifier (comparator_dut_analog) into a StrongARM latch with
* isolation inverters and a NOR SR output latch (comparator_dut_latch).
* aop/aon are the preamplifier outputs and the latch inputs; nothing else
* connects to them, which is what makes the offset-MC and preamp-noise
* benches able to drive the front end on its own.
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
C {comparator_dut_analog.sym} 0 0 0 0 {name=A}
N -110 -90 -190 -90 {lab=vinp}
C {devices/lab_pin.sym} -190 -90 0 0 {name=A_vinp lab=vinp}
N -110 -30 -190 -30 {lab=vinn}
C {devices/lab_pin.sym} -190 -30 0 0 {name=A_vinn lab=vinn}
N -110 30 -190 30 {lab=ibias}
C {devices/lab_pin.sym} -190 30 0 0 {name=A_ibias lab=ibias}
N 110 -90 190 -90 {lab=aop}
C {devices/lab_pin.sym} 190 -90 0 0 {name=A_aop lab=aop}
N 110 -30 190 -30 {lab=aon}
C {devices/lab_pin.sym} 190 -30 0 0 {name=A_aon lab=aon}
N 110 30 190 30 {lab=vdd}
C {devices/lab_pin.sym} 190 30 0 0 {name=A_vdd lab=vdd}
N 110 90 190 90 {lab=vss}
C {devices/lab_pin.sym} 190 90 0 0 {name=A_vss lab=vss}
C {comparator_dut_latch.sym} 600 0 0 0 {name=L}
N 490 -90 410 -90 {lab=aop}
C {devices/lab_pin.sym} 410 -90 0 0 {name=L_inp lab=aop}
N 490 -30 410 -30 {lab=aon}
C {devices/lab_pin.sym} 410 -30 0 0 {name=L_inn lab=aon}
N 490 30 410 30 {lab=clk}
C {devices/lab_pin.sym} 410 30 0 0 {name=L_clk lab=clk}
N 710 -90 790 -90 {lab=dout}
C {devices/lab_pin.sym} 790 -90 0 0 {name=L_dout lab=dout}
N 710 -30 790 -30 {lab=doutb}
C {devices/lab_pin.sym} 790 -30 0 0 {name=L_doutb lab=doutb}
N 710 30 790 30 {lab=vdd}
C {devices/lab_pin.sym} 790 30 0 0 {name=L_vdd lab=vdd}
N 710 90 790 90 {lab=vss}
C {devices/lab_pin.sym} 790 90 0 0 {name=L_vss lab=vss}
