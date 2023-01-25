import time
from nostrpaydm import NostrPayDM

np = NostrPayDM()

try:
    np.connect_relays()
    print("Relays connected")

    while True:
        np.update()
        time.sleep(5)

except KeyboardInterrupt:
    print("Shutting down")
except Exception:
    import traceback
    traceback.print_exc()
finally:
    print("Attempting to disconnect")
    np.disconnect_relays()
    print("Disconnected!")
