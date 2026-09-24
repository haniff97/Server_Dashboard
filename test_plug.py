# test_plug.py
import tinytuya

plug = tinytuya.OutletDevice(
    dev_id='a3f2f187ed028f5920seoc',
    address='192.168.1.2',
    local_key='-rU&}hvPr8G#&!?s',
    version=3.5
)
plug.set_socketPersistent(True)

status = plug.status()
dps = status.get('dps', {})

print(f"Switch  : {'ON' if dps.get('1') else 'OFF'}")
print(f"Voltage : {dps.get('20', 0) / 10} V")
print(f"Current : {dps.get('18', 0)} mA")
print(f"Power   : {dps.get('19', 0) / 10} W")
print(f"Add ele : {dps.get('17', 0) / 1000} kWh")
