# import esp
# esp.osdebug(None)
# import webrepl
# webrepl.start()

print("Booted")

from ph4_sense.sense_mp import main  # noqa: E402

main()
