import logging
import struct
from io import BytesIO
from socket import socket, AF_INET, SOCK_DGRAM
from typing import Union

import networkzero as nw0
from PIL import Image

from create_logger import create_logger

logger = create_logger(name=__name__, level=logging.DEBUG)


class RemotePiCam:
    """
    A class to manage connecting, getting images, and controlling a remote
    PiCam.
    """

    def __init__(self, cam_name: str, port: int):
        """
        Initiate the PiCam. This does not actually connect to the PiCam until
        you call connect().

        :param cam_name: The name of the PiCamera. This is used to discover
         the camera.
        :param port: The port to listen on.
        """
        self._cam_name = cam_name
        self._cam_address = None
        self._port = port
        self._server_socket = None
        self._connection = None
        self._connected = False
        self.settings = {
            "awb_mode": {
                "selected": "auto",
                "available": [
                    "off",
                    "auto",
                    "sunlight",
                    "cloudy",
                    "shade",
                    "tungsten",
                    "fluorescent",
                    "incandescent",
                    "flash",
                    "horizon"
                ]
            },
            "brightness": {
                "min": 0,
                "max": 100,
                "value": 50
            },
            "contrast": {
                "min": -100,
                "max": 100,
                "value": 0
            },
            "effect": {
                "selected": "none",
                "available": [
                    "none",
                    "negative",
                    "solarize",
                    "sketch",
                    "denoise",
                    "emboss",
                    "oilpaint",
                    "hatch",
                    "gpen",
                    "pastel",
                    "watercolor",
                    "film",
                    "blur",
                    "saturation",
                    "colorswap",
                    "washedout",
                    "posterise",
                    "colorpoint",
                    "colorbalance",
                    "cartoon",
                    "deinterlace1",
                    "deinterlace2"
                ]
            },
            "iso": {
                "selected": 0,
                "available": [
                    0,
                    100,
                    200,
                    320,
                    400,
                    500,
                    640,
                    800
                ]
            },
            "resolution": {
                "selected": (720, 480),
                "available": [
                    "128x96",
                    "160x120",
                    "160x144",
                    "176x144",
                    "180x132",
                    "180x135",
                    "192x144",
                    "234x60",
                    "256x192",
                    "320x200",
                    "320x240",
                    "320x288",
                    "320x400",
                    "352x288",
                    "352x240",
                    "384x256",
                    "384x288",
                    "392x72",
                    "400x300",
                    "460x55",
                    "480x320",
                    "468x32",
                    "468x60",
                    "512x342",
                    "512x384",
                    "544x372",
                    "640x350",
                    "640x480",
                    "640x576",
                    "704x576",
                    "720x350",
                    "720x400",
                    "720x480",
                    "720x483",
                    "720x484",
                    "720x486",
                    "720x540",
                    "720x576",
                    "729x348",
                    "768x576",
                    "800x600",
                    "832x624",
                    "856x480",
                    "896x600",
                    "960x720",
                    "1024x576",
                    "1024x768",
                    "1080x720",
                    "1152x768",
                    "1152x864",
                    "1152x870",
                    "1152x900",
                    "1280x720",
                    "1280x800",
                    "1280x854",
                    "1280x960",
                    "1280x992",
                    "1280x1024",
                    "1360x766",
                    "1365x768",
                    "1366x768",
                    "1365x1024",
                    "1400x788",
                    "1400x1050",
                    "1440x900",
                    "1520x856",
                    "1536x1536",
                    "1600x900",
                    "1600x1024",
                    "1600x1200",
                    "1792x1120",
                    "1792x1344",
                    "1824x1128",
                    "1824x1368",
                    "1856x1392",
                    "1920x1080",
                    "1920x1200",
                    "1920x1440",
                    "2000x1280",
                    "2048x1152",
                    "2048x1536",
                    "2048x2048",
                    "2500x1340",
                    "2560x1600",
                    "3072x2252",
                    "3600x2400"
                ]
            },
            "saturation": {
                "min": -100,
                "max": 100,
                "value": 0
            },
            "servos": {
                "enable": True,
                "pan": {
                    "min": 0,
                    "max": 180,
                    "value": 90
                },
                "tilt": {
                    "min": 0,
                    "max": 60,
                    "value": 30
                }
            }
        }

    def _get_ip_addr(self) -> str:
        """
        Get the IP address of this machine.

        :return: A str.
        """
        s = socket(AF_INET, SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
        finally:
            s.close()

    def connect(self, timeout: int = 30) -> bool:
        """
        Actually connect to the PiCam.

        :param timeout: Wait up to x amount of seconds before giving up.
        :return: A bool on whether we successfully connected or not.
        """
        logger.debug(f"Attempting to connect to a PiCam with name "
                     f"{self._cam_name}")
        try:
            service = nw0.discover(self._cam_name, timeout)
        except nw0.core.SocketTimedOutError:
            return False
        if service is None:
            logger.warning("Failed to find PiCam")
            return False
        else:
            logger.info(f"Successfully connected to PiCam '{self._cam_name}' "
                        f"at address {service}")
            logger.debug(f"Opening socket on port {self._port}")
            self._server_socket = socket()
            self._server_socket.bind(("0.0.0.0", self._port))
            self._server_socket.listen(0)
            self.settings = nw0.send_message_to(service, self._get_ip_addr())
            self._cam_address = service
            self._connection = self._server_socket.accept()[0].makefile("rb")
            self._connected = True
            return True

    def get_image(self) -> Union[tuple[Image.Image, int], None]:
        """
        Get an image from the PiCam.

        :return: A tuple of a PIL.Image and the size, or None if disconnected.
        """
        failed = False
        if not self.is_connected:
            raise ValueError("Not connected")
        try:
            u32_size = struct.calcsize("<L")
            img_len = struct.unpack("<L", self._connection.read(u32_size))[0]
            if img_len == 0:
                raise ValueError("No more data is being sent, closing")
            img_stream = BytesIO()
            img_stream.write(self._connection.read(img_len))
            img_stream.seek(0)
            img_pil = Image.open(img_stream)
            return img_pil, img_len
        except Exception:
            failed = True
        finally:
            if failed:
                self._connection.close()
                self._server_socket.close()
                self._connected = False
        return None

    def update_settings(self) -> bool:
        """
        Update the settings.

        :return: A bool on whether the settings were set or not.
        """
        result = nw0.send_message_to(self._cam_address, self.settings)
        self.settings = result[1]
        return result[0]

    def disconnect(self) -> None:
        """
        Disconnect.

        :return: None.
        """
        logger.warning("Disconnecting")
        self._connection.close()
        self._server_socket.close()
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """
        Get whether we are currently connected to a PiCam or not.

        :return: A bool.
        """
        return self._connected
