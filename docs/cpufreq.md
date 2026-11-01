# CPU frequency and overclock test (2026-11-01)

## Default: 996 MHz (rated)
Mainline `imx6q-cpufreq` with the `imx6sl.dtsi` operating points, through the SoC's internal LDOs (`reg_arm`,
`reg_soc`) fed by BD71815 buck2/buck1 at 1.3 V. Governor ondemand; idles at 396 MHz.

| kHz | VDD_ARM | VDD_SOC/PU |
|---|---|---|
| 996 000 | 1.275 V | 1.225 V |
| 792 000 | 1.175 V | 1.175 V |
| 396 000 | 0.975 V | 1.175 V |

Speed-grade fuse (OCOTP_CFG3 bits 17:16) = 2 → this part is rated for 996 MHz. Stock Amazon uses buck2/buck1
directly as arm/soc supply (996 MHz @ 1.275 V, 396 MHz @ 0.975 V); mainline's LDO path gives the same targets.

## Benchmarks (single core; y-cruncher has no 32-bit ARM build)
`host/bench.sh`: π to 3000 digits with `bc -l` (digits SHA-256 compared with the same computation on a PC)
and `sysbench cpu --cpu-max-prime=20000` for 30 s.

| | 792 MHz | 996 MHz | 1104 MHz |
|---|---|---|---|
| stress-ng int64 (compute-bound) | 90.2 /s | 114.0 /s | — |
| stress-ng matrixprod (memory-bound) | 34.5 /s | 37.1 /s | — |
| π 3000 digits | 170 s ✓ (396 MHz: 302 s ✓) | 144 s ✓ | 132 s ✓ |
| sysbench primes | 13.50 /s (396 MHz: 6.71 /s) | 16.80 /s | 18.18 /s |
| SoC after benchmark | — | 47.6 °C | 48.7 °C |

## Overclock: 1104 MHz (default since 2026-11-01)
`kernel/overclock-1104.dtsi` adds 1104 MHz (PLL1 = 24 MHz × 92 / 2) at 1.3 V, the VDD_ARM_CAP maximum; the
LDO input is 1.3 V, so the real core voltage is slightly lower. Included by the board DTS; remove the `#include` to go back to 996 MHz.
- clock confirmed: pll1_sys = arm = 1 104 000 000 Hz, vddarm 1 300 000 µV
- 10 min `stress-ng --cpu 1 --cpu-method all --vm 1 --vm-bytes 96M --vm-method all --verify` pinned at 1104 MHz:
  **passed, 0 failures, 0 untrustworthy metrics, no kernel errors**
- SoC temperature: 43.5 °C start, 47–48 °C plateau (max 48.1 °C), far below the 85 °C passive trip
- Gain: about +8 % (π −8.3 % time, sysbench +8.2 %) for +10.8 % clock

One unit, one 10-minute run: not a qualification. The part is fused for 996 MHz; running above it is outside
NXP's specification and may shorten the chip's life or show errors under other conditions.
