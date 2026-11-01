import serial, sys, time
# usage: ser.py "<command>" [timeout_s] [idle_s]
cmd = sys.argv[1]; tmo = float(sys.argv[2]) if len(sys.argv)>2 else 5; idle=float(sys.argv[3]) if len(sys.argv)>3 else 1.0
s = serial.Serial('/dev/ttyACM0', 115200, timeout=0.1)
s.reset_input_buffer()
for ch in (cmd + '\r').encode():
    s.write(bytes([ch])); time.sleep(0.003)
out=b''; start=time.time(); last=time.time()
while time.time()-start < tmo:
    d = s.read(4096)
    if d: out+=d; last=time.time()
    elif time.time()-last > idle and out: break
sys.stdout.write(out.decode(errors='replace'))
