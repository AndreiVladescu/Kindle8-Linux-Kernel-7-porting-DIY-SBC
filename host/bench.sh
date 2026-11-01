#!/bin/sh
# CPU benchmark for the Kindle 8 SBC (runs on the device). y-cruncher has no 32-bit ARM build, so:
#  - pi to N digits with bc (arbitrary precision, single core), timed; digits hashed for verification
#  - sysbench cpu (prime search, 1 thread, 30 s)
# Prints frequency and SoC temperature before/after.
N=${1:-3000}
C=/sys/devices/system/cpu/cpu0/cpufreq
T=$(for z in /sys/class/thermal/thermal_zone*; do [ "$(cat $z/type)" = imx_thermal_zone ] && echo $z; done)
temp() { awk '{printf "%.1f", $1/1000}' $T/temp; }
echo "freq: $(cat $C/scaling_cur_freq) kHz (governor $(cat $C/scaling_governor)), SoC $(temp) C"
s=$(date +%s.%N)
digits=$(echo "scale=$N; 4*a(1)" | bc -l | tr -d '\\\n')
e=$(date +%s.%N)
echo "pi $N digits: $(echo "$e - $s" | bc) s, sha256 $(printf %s "$digits" | sha256sum | cut -c1-16)"
echo "sysbench primes: $(sysbench cpu --threads=1 --time=30 --cpu-max-prime=20000 run | awk '/events per second/{print $4}') events/s"
echo "after: SoC $(temp) C, freq $(cat $C/scaling_cur_freq) kHz"
