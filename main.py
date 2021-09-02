import logging
import queue
import tkinter as tk
from threading import Thread
from queue import Queue

from PIL import ImageTk, Image
from TkZero.Label import Label, DisplayModes
from TkZero.MainWindow import MainWindow

from create_logger import create_logger
from picam import RemotePiCam

logger = create_logger(name=__name__, level=logging.DEBUG)

cam_name = "picam"
port = 7896


class RemotePiCamGUI(MainWindow):
    def __init__(self):
        super().__init__()
        self.title = "Remote PiCam"
        self.create_gui()
        self.on_close = self.close_window
        self.image_queue = Queue(maxsize=32)
        self.cam = RemotePiCam(cam_name, port)
        self.spawn_connect_thread()

    def create_gui(self) -> None:
        """
        Create the GUI.

        :return: None.
        """
        logger.debug("Creating GUI elements")
        self.image_label = Label(self)
        self.image_label.display_mode = DisplayModes.ImageOnly
        blank_image = Image.new("RGBA", (720, 480))
        self.image_label.image = ImageTk.PhotoImage(blank_image)
        self.image_label.grid(row=0, column=0, padx=1, pady=1, sticky=tk.NW)
        self.status_label = Label(self, text="Nothing to do yet")
        self.status_label.grid(row=1, column=0, padx=1, pady=1, sticky=tk.NW)

    def close_window(self) -> None:
        """
        Close the GUI.

        :return: None.
        """
        if self.cam.is_connected:
            self.disconnect()
        self.destroy()

    def spawn_connect_thread(self) -> None:
        """
        Spawn the connection thread.

        :return: None.
        """
        logger.debug("Spawning connection thread")
        t = Thread(target=self.connect, daemon=True)
        t.start()

    def connect(self) -> None:
        """
        Connect to the PiCam.

        :return: None.
        """
        logger.debug(f"Attempting to connect to PiCam {cam_name} port {port}")
        self.status_label.text = "Attempting to connect to the PiCam..."
        while not self.cam.connect():
            pass
        logger.info("Connected successfully!")
        self.status_label.text = "Connected successfully!"
        self.start_update_cam_thread()

    def update_image(self) -> None:
        """
        Pull and update the image on the window. You should only call this
        once.

        :return: None.
        """
        try:
            self.image_label.image = self.image_queue.get_nowait()
        except queue.Empty:
            pass
        self.after(50, self.update_image)

    def start_update_cam_thread(self) -> None:
        """
        Start the update the camera thread.

        :return: None.
        """
        logger.debug("Spawning update thread")
        t = Thread(target=self.update_cam, daemon=True)
        t.start()
        self.update_image()

    def update_cam(self) -> None:
        """
        Update the camera.

        :return: None.
        """
        try:
            while self.cam.is_connected:
                image = self.cam.get_image()
                if self.image_queue.full():
                    self.image_queue.get()
                if image is None:
                    break
                self.image_queue.put(ImageTk.PhotoImage(image))
        finally:
            self.spawn_disconnect_thread()

    def spawn_disconnect_thread(self) -> None:
        """
        Spawn the disconnect thread.

        :return: None.
        """
        logger.warning("Spawning disconnect thread")
        t = Thread(target=self.disconnect, daemon=True)
        t.start()

    def disconnect(self) -> None:
        """
        Disconnect from the PiCam.

        :return: None.
        """
        self.status_label.text = "Disconnecting..."
        self.cam.disconnect()
        self.status_label.text = "Disconnected."


logger.debug("Creating GUI")
gui = RemotePiCamGUI()
gui.mainloop()
