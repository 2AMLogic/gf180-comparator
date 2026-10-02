# comparator comp data (generated, public-sources-only)

Generated 2026-10-02 from the upstream comp library's `comparator.md` entry by an internal, private-repo-only tool. This is a derived, filtered copy — regenerate rather than hand-edit. Every source row below cites a public vendor datasheet, distributor page, standards document, paper, or public repository; nothing internal survived extraction.

## Comparable parts

| Vendor | Part | Class | Supply | Input offset | Decision / propagation time | Supply current | Package | Price (1–99 / 1000+) | Source |
|---|---|---|---|---|---|---|---|---|---|
| Texas Instruments | TLV3603 (TLV360x family) | 325 MHz high-speed comparator **with latch (LE) and adjustable-hysteresis pin** — the only latched part in this set | 2.4–5.5 V | ±0.5 mV typ, ±5 mV max over −40…125 °C | 2.5 ns typ / 3.5 ns max at 25 °C, 4.5 ns max over −40…125 °C, at 50 mV overdrive & underdrive; overdrive dispersion 600 ps over a 10→125 mV sweep | 5.7 mA typ, 7.8 mA max | SC70-6 | $3.893 / $2.116 (TLV3603DCKR) | Datasheet: [ti.com/lit/ds/symlink/tlv3601.pdf](https://www.ti.com/lit/ds/symlink/tlv3601.pdf) (SNOSDB1E, rev. April 2023). Pricing: [ti.com/product/TLV3603](https://www.ti.com/product/TLV3603) |
| Texas Instruments | TLV3501 (TLV350x family) | 4.5 ns rail-to-rail push-pull comparator with shutdown | 2.7–5.5 V | ±1 mV typ, ±6.5 mV max (V_CM = 0 V, I_O = 0 mA); 6 mV typ internal hysteresis | 4.5 ns typ / 6.4 ns max at 25 °C at 20 mV overdrive (7 ns max over −40…125 °C); 7.5 ns typ / 10 ns max at 5 mV overdrive; f_MAX 80 MHz at 50 mV overdrive, 5 V | 3.2 mA typ, 5 mA max at 5 V | SOT-23-6 / SO-8 | $3.204 / $1.586 (TLV3501AIDBVR) | Datasheet: [ti.com/lit/ds/symlink/tlv3501.pdf](https://www.ti.com/lit/ds/symlink/tlv3501.pdf) (SBOS321E, rev. April 2016). Pricing: [ti.com/product/TLV3501](https://www.ti.com/product/TLV3501) |
| Texas Instruments | LMV7219 | 7 ns comparator with internal hysteresis, rail-to-rail output | 2.7–5 V | 1 mV typ, 6 mV max at 5 V (8 mV max over −40…85 °C); 7.5 mV typ hysteresis | 7 ns typ / 19 ns max at 50 mV overdrive, 5 V; 8 ns at 15 mV; 9 ns at 5 mV | 1.1 mA typ, 1.8 mA max at 5 V | SC70-5 / SOT-23-5 | $2.928 / $1.307 (LMV7219M5/NOPB) | Datasheet: [ti.com/lit/ds/symlink/lmv7219.pdf](https://www.ti.com/lit/ds/symlink/lmv7219.pdf) (SNOS458I, rev. June 2016). Pricing: [ti.com/product/LMV7219](https://www.ti.com/product/LMV7219) |
| Texas Instruments | TLV3691 | Nanopower comparator — the only part here whose supply range reaches a 1.2 V core rail | 0.9–6.5 V | ±3 mV typ, ±15 mV max at 25 °C, ±22 mV max over −40…125 °C; 17 mV typ hysteresis | 24 µs typ at 6.5 V / 100 mV overdrive; 35 µs at 0.9 V / 100 mV; 32 µs at 6.5 V / 50 mV; 40–45 µs at 0.9 V / 50 mV | 75 nA typ, 150 nA max at 25 °C (200 nA max over temp) | SC70-5 / X2SON-6 (1.0 × 1.0 mm) | $1.065 / $0.431 (TLV3691IDCKR) | Datasheet: [ti.com/lit/ds/symlink/tlv3691.pdf](https://www.ti.com/lit/ds/symlink/tlv3691.pdf) (SBOS694A, rev. November 2015). Pricing: [ti.com/product/TLV3691](https://www.ti.com/product/TLV3691) |

## Sources

| URL | Establishes | Fetched |
|---|---|---|
| https://www.ti.com/lit/ds/symlink/tlv3601.pdf | TLV3601/2/3 offset, propagation delay, overdrive dispersion, latch pin, supply current, package (SNOSDB1E) | 2026-09-24 |
| https://www.ti.com/product/TLV3603 | TLV3603DCKR published tiered direct pricing | 2026-09-24 |
| https://www.ti.com/lit/ds/symlink/tlv3501.pdf | TLV3501 offset, hysteresis, propagation delay vs. overdrive, f_MAX, I_Q, package (SBOS321E) | 2026-09-24 |
| https://www.ti.com/product/TLV3501 | TLV3501AIDBVR published tiered direct pricing | 2026-09-24 |
| https://www.ti.com/lit/ds/symlink/lmv7219.pdf | LMV7219 offset, hysteresis, propagation delay vs. overdrive, supply current, package (SNOS458I) | 2026-09-24 |
| https://www.ti.com/product/LMV7219 | LMV7219M5/NOPB published tiered direct pricing | 2026-09-24 |
| https://www.ti.com/lit/ds/symlink/tlv3691.pdf | TLV3691 supply range, offset, hysteresis, response time, quiescent current, package (SBOS694A) | 2026-09-24 |
| https://www.ti.com/product/TLV3691 | TLV3691IDCKR published tiered direct pricing | 2026-09-24 |

