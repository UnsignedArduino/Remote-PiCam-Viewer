import logging

from create_logger import create_logger
from picam import RemotePiCam

logger = create_logger(name=__name__, level=logging.DEBUG)

cam_name = "picam"
port = 7896

try:
    cam = RemotePiCam(cam_name, port)
    logger.debug(f"Attempting to connect to PiCam {cam_name} port {port}")
    while not cam.connect():
        pass
    logger.info("Connected successfully!")
    logger.debug("Now streaming")
    while cam.is_connected:
        cam.get_image()
finally:
    cam.disconnect()
