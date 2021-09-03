import logging
import queue
import tkinter as tk
from queue import Queue
from threading import Thread

from PIL import ImageTk, Image
from TkZero.Button import Button
from TkZero.Dialog import CustomDialog
from TkZero import Dialog
from TkZero.Label import Label, DisplayModes
from TkZero.MainWindow import MainWindow
from TkZero.Menu import Menu, MenuCascade, MenuCommand, MenuSeparator, \
    MenuCheckbutton
from TkZero.Progressbar import Progressbar, ProgressModes
from TkZero.Vector import Position

from create_logger import create_logger
from picam import RemotePiCam

logger = create_logger(name=__name__, level=logging.DEBUG)

cam_name = "picam"
port = 7896


class RemotePiCamGUI(MainWindow):
    def __init__(self):
        self.connecting = False
        self.stop_try = False
        self.image_queue = Queue(maxsize=32)
        self.curr_img = None
        self.cam = RemotePiCam(cam_name, port)
        super().__init__()
        self.title = "Remote PiCam"
        self.resizable(False, False)
        self.create_gui()
        self.create_menu()
        self.on_close = self.close_window
        self.update_image()
        self.lift()

    def create_gui(self) -> None:
        """
        Create the GUI.

        :return: None.
        """
        logger.debug("Creating GUI elements")

        self.image_label = Label(self)
        self.image_label.display_mode = DisplayModes.ImageOnly
        self.image_label.image = ImageTk.PhotoImage(
            Image.new("RGBA", (300, 50))
        )
        self.image_label.grid(row=0, column=0, padx=1, pady=1, sticky=tk.NW)

        self.status_label = Label(self, text="Nothing to do yet")
        self.status_label.grid(row=1, column=0, padx=1, pady=1, sticky=tk.SW)

    def create_menu(self) -> None:
        """
        Create the menu.

        :return: None.
        """
        logger.debug("Creating menu")
        self.stream_paused_var = tk.BooleanVar(self, value=False)
        self.stream_paused_var.trace_add("write", self.update_paused_status)
        self.menu_bar = Menu(self, is_menubar=True, command=self.remake_menu)
        self.remake_menu()

    def remake_menu(self) -> None:
        """
        Remake the menus.

        :return: None.
        """
        logger.debug("Redrawing menus")
        logger.debug(f"Connected: {self.cam.is_connected}")
        self.menu_bar.items = [
            MenuCascade(label="File", items=[
                MenuCommand(label="Connect", underline=0,
                            enabled=not self.cam.is_connected and
                                    not self.connecting,
                            command=self.start_connecting_window),
                MenuCommand(label="Disconnect", underline=0,
                            enabled=self.cam.is_connected,
                            command=self.spawn_disconnect_thread),
                MenuSeparator(),
                MenuCommand(label="Exit", underline=0,
                            command=self.close_window)
            ]),
            MenuCascade(label="Stream", items=[
                MenuCheckbutton(label="Stream paused", underline=7,
                                enabled=self.cam.is_connected,
                                variable=self.stream_paused_var),
                MenuSeparator(),
                MenuCommand(label="Take photo", underline=0,
                            enabled=self.curr_img is not None,
                            command=self.take_photo)
            ]),
        ]

    def update_paused_status(self, *args) -> None:
        """
        Update the status bar when we pause or resume the stream.

        :return: None.
        """
        if self.stream_paused_var.get():
            self.status_label.text = "Paused."
        else:
            self.status_label.text = "Resume."

    def take_photo(self) -> None:
        """
        Take a photo of the stream and show a dialog on what you want to do
        with it.

        :return: None.
        """
        self.photo_taken = self.curr_img.copy()
        self.photo_window = CustomDialog(self)
        self.photo_window.title = "Take a photo"
        self.photo_window.resizable(False, False)
        photo_taken_lbl = Label(self.photo_window,
                                text="Photo taken! What would you like to "
                                     "do with it?")
        photo_taken_lbl.grid(row=0, column=0, columnspan=3, padx=1, pady=1,
                             sticky=tk.NW)
        photo_thumbnail_lbl = Label(self.photo_window)
        photo_thumbnail_lbl.display_mode = DisplayModes.ImageOnly
        thumbnail = self.photo_taken.copy()
        thumbnail.thumbnail((320, 240))
        photo_thumbnail_lbl.image = ImageTk.PhotoImage(thumbnail)
        photo_thumbnail_lbl.grid(row=1, column=0, columnspan=3, padx=1, pady=1,
                                 sticky=tk.NW)
        self.show_photo_btn = Button(self.photo_window,
                                     text="Show in image viewer",
                                     command=self.photo_taken.show)
        self.show_photo_btn.grid(row=2, column=0, padx=1, pady=1,
                                 sticky=tk.NW + tk.E)
        self.save_photo_btn = Button(self.photo_window,
                                     text="Save to file",
                                     command=self.save_photo_taken)
        self.save_photo_btn.grid(row=2, column=1, padx=1, pady=1,
                                 sticky=tk.NW + tk.E)
        self.close_btn = Button(self.photo_window,
                                text="Close",
                                command=self.photo_window.close)
        self.close_btn.grid(row=2, column=2, padx=1, pady=1,
                            sticky=tk.NW + tk.E)
        self.photo_window.lift()
        self.photo_window.position = Position(
            x=round(self.position.x + (self.size.width / 2) -
                    (self.photo_window.size.width / 2)),
            y=round(self.position.y + (self.size.height / 2) -
                    (self.photo_window.size.height / 2))
        )
        self.photo_window.grab_set()
        self.photo_window.grab_focus()
        self.photo_window.wait_till_destroyed()

    def save_photo_taken(self) -> None:
        """
        Save the current photo to a file after opening a dialog.

        :return: None.
        """
        logger.debug("Asking user to select a location to save photo")
        path = Dialog.save_file(
            title="Select a location to save your photo...",
            file_types=(("Portable Network Graphics (PNG) files", "*.png"),
                        ("JPEG files", "*.jpeg"),
                        ("Graphics Interchange Format (GIF) files", "*.gif"),
                        ("Bitmap (BMP) files", "*.bmp"),
                        ("All files", "*.*"))
        )
        if path is not None:
            logger.info(f"Saving photo to {path}")
            try:
                self.photo_taken.save(path)
            except Exception as e:
                Dialog.show_error(self, title="Remote PiCam: ERROR!",
                                  message="There was an error saving your "
                                          "picture!",
                                  detail=f"Exception: {e}")
            else:
                Dialog.show_info(self, title="Remote PiCam: Success!",
                                 message="Successfully saved photo!",
                                 detail=f"Saved to {path}")

    def close_window(self) -> None:
        """
        Close the GUI.

        :return: None.
        """
        if self.cam.is_connected:
            self.disconnect()
        self.destroy()

    def start_connecting_window(self) -> None:
        """
        Create the connecting window.

        :return: None.
        """
        self.spawn_connect_thread()
        logger.debug("Creating connecting window")
        self.conn_window = CustomDialog(self)
        self.conn_window.title = "Connecting..."
        self.conn_window.resizable(False, False)
        self.connecting_lbl = Label(self.conn_window, text="Connecting...")
        self.connecting_lbl.grid(row=0, column=0, padx=1, pady=1, sticky=tk.NW)
        self.connecting_pb = Progressbar(self.conn_window, length=300,
                                         mode=ProgressModes.Indeterminate)
        self.connecting_pb.grid(row=1, column=0, padx=2, pady=1, sticky=tk.NW)
        self.connecting_pb.start()
        self.cancel_btn = Button(self.conn_window, text="Cancel",
                                 command=self.stop_connecting)
        self.cancel_btn.grid(row=2, column=0, padx=1, pady=1)
        self.conn_window.on_close = self.stop_connecting
        self.conn_window.lift()
        self.conn_window.position = Position(
            x=round(self.position.x + (self.size.width / 2) -
                    (self.conn_window.size.width / 2)),
            y=round(self.position.y + (self.size.height / 2) -
                    (self.conn_window.size.height / 2))
        )
        self.conn_window.grab_focus()
        self.conn_window.wait_till_destroyed()

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
        self.connecting = True
        self.stop_try = False
        logger.debug(f"Attempting to connect to PiCam {cam_name} port {port}")
        self.status_label.text = "Attempting to connect to the PiCam..."
        while not self.cam.connect(timeout=3):
            if self.stop_try:
                logger.warning("Stopped trying to connect.")
                self.status_label.text = "Canceled attempted connection."
                self.stop_try = False
                self.connecting = False
                self.conn_window.destroy()
                return
        logger.info("Connected successfully!")
        self.status_label.text = "Connected successfully!"
        self.connecting = False
        self.status_label.text = "Connected!"
        self.connecting_lbl.text = "Connected!"
        self.connecting_pb.stop()
        self.connecting_pb.max = 1
        self.connecting_pb.value = 1
        self.cancel_btn.enabled = False
        self.after(100, self.conn_window.destroy)
        self.start_update_cam_thread()

    def stop_connecting(self) -> None:
        """
        Stop trying to connect to the PiCam.

        :return: None.
        """
        self.status_label.text = "Canceling attempted connection..."
        self.connecting_lbl.text = "Canceling attempted connection..."
        self.connecting_pb.stop()
        self.connecting_pb.start()
        self.cancel_btn.enabled = False
        self.stop_try = True

    def update_image(self) -> None:
        """
        Pull and update the image on the window. You should only call this
        once.

        :return: None.
        """
        try:
            image = self.image_queue.get_nowait()
            self.curr_img = image
            self.image_label.image = ImageTk.PhotoImage(image)
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
                if not self.stream_paused_var.get():
                    self.image_queue.put(image)
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
