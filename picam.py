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
            "resolution": (720, 480)
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
        logger.debug(f"Opening socket on port {self._port}")
        self._server_socket = socket()
        self._server_socket.bind(("0.0.0.0", self._port))
        self._server_socket.listen(0)
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
            nw0.send_message_to(service, self._get_ip_addr())
            self._cam_address = service
            self._connection = self._server_socket.accept()[0].makefile("rb")
            self._connected = True
            return True

    def get_image(self) -> Union[Image.Image, None]:
        """
        Get an image from the PiCam.

        :return: A PIL.Image, or None if disconnected.
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
            return img_pil
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
