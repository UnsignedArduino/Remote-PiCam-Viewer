from json import loads as load_json, dumps as dump_json
import logging
import queue
import tkinter as tk
import webbrowser
from pathlib import Path
from queue import Queue
from threading import Thread

from PIL import ImageTk, Image
from TkZero import Dialog
from TkZero.Button import Button
from TkZero.Combobox import Combobox
from TkZero.Dialog import CustomDialog
from TkZero.Frame import Frame
from TkZero.Label import Label, DisplayModes
from TkZero.MainWindow import MainWindow
from TkZero.Menu import Menu, MenuCascade, MenuCommand, MenuSeparator, \
    MenuCheckbutton, MenuRadiobutton
from TkZero.Progressbar import Progressbar, ProgressModes
from TkZero.Scale import Scale, OrientModes
from TkZero.Vector import Position

from create_logger import create_logger
from picam import RemotePiCam

logger = create_logger(name=__name__, level=logging.DEBUG)

SETTINGS_PATH = Path.cwd() / "settings.json"


class RemotePiCamGUI(MainWindow):
    def __init__(self):
        self.connecting = False
        self.stop_try = False
        self.image_queue = Queue(maxsize=32)
        self.curr_img = None
        self.settings = {}
        self.load_settings()
        self.cam = RemotePiCam(self.settings["camera"]["name"],
                               self.settings["camera"]["port"])
        super().__init__()
        self.title = "Remote PiCam Viewer"
        self.resizable(False, False)
        theme_path = Path.cwd() / "sun-valley.tcl"
        self.has_theme = theme_path.exists()
        if self.has_theme:
            logger.info(f"Importing theme file {theme_path}")
            self.tk.call("source", str(theme_path.expanduser().resolve()))
            self.tk.call("set_theme", "light")
        else:
            logger.warning(f"{theme_path} does not exist, unable to set "
                           f"theme!")
        self.create_gui()
        self.create_menu()
        self.dark_mode_var.set(self.settings["gui"]["dark_mode"])
        self.on_close = self.close_window
        self.update_image()
        self.lift()

    def load_settings(self) -> None:
        """
        Load the settings from a file.

        :return: None.
        """
        logger.info(f"Loading settings from {SETTINGS_PATH}")
        defaults = {
            "camera": {
                "name": "picam",
                "port": 7896
            },
            "gui": {
                "dark_mode": False
            }
        }
        if not SETTINGS_PATH.exists():
            logger.warning("Settings file does not exist, creating!")
            SETTINGS_PATH.write_text(dump_json(defaults, indent=4))
        self.settings = defaults | load_json(SETTINGS_PATH.read_text())

    def save_settings(self) -> None:
        """
        Set the current settings and save it to a file.

        :return: None.
        """
        logger.debug(f"Saving new settings to {SETTINGS_PATH}")
        SETTINGS_PATH.write_text(dump_json(self.settings, indent=4))

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
        self.awb_mode_var = tk.StringVar(self, value="auto")
        self.awb_mode_var.trace_add("write", self.update_awb_status)
        self.effect_var = tk.StringVar(self, value="none")
        self.effect_var.trace_add("write", self.update_effect_status)
        self.iso_var = tk.IntVar(self, value=0)
        self.iso_var.trace_add("write", self.update_iso_status)
        self.dark_mode_var = tk.BooleanVar(self, value=False)
        self.dark_mode_var.trace_add("write", self.toggle_theme)
        self.menu_bar = Menu(self, is_menubar=True, command=self.remake_menu)
        self.remake_menu()

    def toggle_theme(self, *args) -> None:
        """
        Toggle the theme between light and dark mode.

        :return: None.
        """
        if self.has_theme:
            if not self.dark_mode_var.get():
                logger.debug("Switching to light mode")
                self.settings["gui"]["dark_mode"] = False
                self.tk.call("set_theme", "light")
            else:
                logger.debug("Switching to dark mode")
                self.settings["gui"]["dark_mode"] = True
                self.tk.call("set_theme", "dark")
            self.save_settings()

    def remake_menu(self) -> None:
        """
        Remake the menus.

        :return: None.
        """
        logger.debug("Redrawing menus")
        logger.debug(f"Connected: {self.cam.is_connected}")
        available_awb_modes = []
        for mode in self.cam.settings["awb_mode"]["available"]:
            if mode == "off":
                continue
            available_awb_modes.append(MenuRadiobutton(
                value=mode,
                label=mode.title(),
                variable=self.awb_mode_var,
                enabled=self.cam.is_connected
            ))
        available_effects = []
        for effect in self.cam.settings["effect"]["available"]:
            available_effects.append(MenuRadiobutton(
                value=effect,
                label=effect.title(),
                variable=self.effect_var,
                enabled=self.cam.is_connected
            ))
        available_iso = []
        for iso in self.cam.settings["iso"]["available"]:
            available_iso.append(MenuRadiobutton(
                value=iso,
                label="Auto" if iso == 0 else str(iso),
                variable=self.iso_var,
                enabled=self.cam.is_connected
            ))
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
                            command=self.take_photo),
                MenuSeparator(),
                MenuCascade(label="Set auto-white balance mode", underline=4,
                            items=available_awb_modes),
                MenuCommand(label="Set brightness", underline=4,
                            enabled=self.cam.is_connected,
                            command=self.set_brightness),
                MenuCommand(label="Set contrast", underline=4,
                            enabled=self.cam.is_connected,
                            command=self.set_contrast),
                MenuCascade(label="Set image effect mode", underline=4,
                            items=available_effects),
                MenuCascade(label="Set ISO", underline=6,
                            items=available_iso),
                MenuCommand(label="Set resolution", underline=4,
                            enabled=self.cam.is_connected,
                            command=self.set_resolution),
                MenuCommand(label="Set saturation", underline=4,
                            enabled=self.cam.is_connected,
                            command=self.set_saturation),
            ]),
            MenuCascade(label="Control", items=[
                MenuCommand(label="Open pan-tilt control panel",
                            underline=14,
                            enabled=self.cam.is_connected,
                            command=self.open_pan_tilt_control_panel)
            ]),
            MenuCascade(label="View", items=[
                MenuCheckbutton(label="Dark mode",
                                variable=self.dark_mode_var,
                                enabled=self.has_theme)
            ]),
            MenuCascade(label="Help", items=[
                self.make_menu_path("Open settings file", SETTINGS_PATH),
                MenuSeparator(),
                self.make_menu_link("Remote PiCam Viewer",
                                    "https://github.com/UnsignedArduino/Remote-PiCam-Viewer"),
                self.make_menu_link("Remote PiCam",
                                    "https://github.com/UnsignedArduino/Remote-PiCam")
            ])
        ]

    def make_menu_link(self, label: str, link: str) -> MenuCascade:
        """
        Make a MenuCascade that can open a link in the browser or copy it to
        the clipboard.

        :param label: What to call the MenuCascade.
        :param link: The actual link.
        :return: A MenuCascade.
        """
        return MenuCascade(label=label, items=[
            MenuCommand(label=link,
                        enabled=False),
            MenuSeparator(),
            MenuCommand(label="Open link in default browser",
                        underline=0,
                        command=lambda: webbrowser.open(link)),
            MenuCommand(label="Copy link to clipboard",
                        underline=0,
                        command=lambda: self.copy_to_clipboard(link))
        ])

    def make_menu_path(self, label: str, path: Path) -> MenuCascade:
        """
        Make a MenuCascade that can open a path in the default application, (if
        a file) open in a file explorer, or copy the path to the clipboard.

        :param label: What to call the MenuCascade.
        :param path: The actual path.
        :return: A MenuCascade.
        """
        menu_items = [
            MenuCommand(label=str(path),
                        enabled=False),
            MenuSeparator(),
        ]
        if path.is_file() or str("." in path.name):
            menu_items += [
                MenuCommand(label="Open file in default application",
                            underline=0,
                            command=lambda: webbrowser.open(str(path)),
                            enabled=path.exists()),
                MenuCommand(label="Open containing directory in default "
                                  "file manager",
                            underline=16,
                            command=lambda: webbrowser.open(str(path.parent)),
                            enabled=path.parent.exists()),
                MenuCommand(label="Copy file path to clipboard",
                            underline=0,
                            command=lambda: self.copy_to_clipboard(str(path)))
            ]
        else:
            menu_items += [
                MenuCommand(label="Open directory in default file manager",
                            underline=0,
                            command=lambda: webbrowser.open(str(path)),
                            enabled=path.exists()),
                MenuCommand(label="Copy directory path to clipboard",
                            underline=0,
                            command=lambda: self.copy_to_clipboard(str(path)))
            ]
        return MenuCascade(label=label, items=menu_items)

    def copy_to_clipboard(self, string: str) -> None:
        """
        Copy a string to the clipboard.

        :param string: A string to copy to the clipboard.
        :return: None.
        """
        self.clipboard_clear()
        self.clipboard_append(string)

    def open_pan_tilt_control_panel(self) -> None:
        """
        Open the pan-tilt control panel.

        :return: None.
        """
        logger.debug("Opening pan-tilt control panel")
        self.pan_tilt_window = CustomDialog(self)
        self.pan_tilt_window.title = "Pan-tilt control panel"
        self.pan_tilt_window.resizable(False, False)
        for i in range(3):
            if i < 2:
                self.pan_tilt_window.columnconfigure(i, weight=1)
            self.pan_tilt_window.rowconfigure(i, weight=1)
        new_pan_tilt = Frame(self.pan_tilt_window)
        new_pan_tilt.grid(row=0, column=0, columnspan=2,
                          sticky=tk.W + tk.E)
        new_pan = Frame(new_pan_tilt)
        new_pan.grid(row=0, column=0, padx=(0, 10))
        pan_lbl = Label(new_pan, text="Pan: ")
        pan_lbl.grid(row=0, column=0, padx=1, pady=1, sticky=tk.NW)
        new_pan_lbl = Label(new_pan, text="0°")
        new_pan_lbl.grid(row=0, column=2, padx=1, pady=1, sticky=tk.NW)

        def update_new_pan_lbl(new_val):
            new_pan_lbl.text = f"{round(new_val)}°"

        self.new_pan_scale = Scale(
            new_pan, length=100,
            minimum=float(self.cam.settings["servos"]["pan"]["min"]),
            maximum=float(self.cam.settings["servos"]["pan"]["max"]),
            command=update_new_pan_lbl
        )
        self.new_pan_scale.grid(row=0, column=1, padx=1, pady=1, sticky=tk.NW)
        self.new_pan_scale.value = float(
            self.cam.settings["servos"]["pan"]["max"])
        new_tilt = Frame(new_pan_tilt)
        new_tilt.grid(row=0, column=1, padx=(10, 0))
        tilt_lbl = Label(new_tilt, text="Tilt: ")
        tilt_lbl.grid(row=0, column=0, padx=1, pady=1, sticky=tk.W)
        new_tilt_lbl = Label(new_tilt, text="0°")
        new_tilt_lbl.grid(row=0, column=2, padx=1, pady=1, sticky=tk.W)

        def update_new_tilt_lbl(new_val):
            new_tilt_lbl.text = f"{round(new_val)}°"

        self.new_tilt_scale = Scale(
            new_tilt, orientation=OrientModes.Vertical, length=50,
            minimum=float(self.cam.settings["servos"]["tilt"]["min"]),
            maximum=float(self.cam.settings["servos"]["tilt"]["max"]),
            command=update_new_tilt_lbl
        )
        self.new_tilt_scale.grid(row=0, column=1, padx=1, pady=1, sticky=tk.NW)
        self.new_tilt_scale.value = float(
            self.cam.settings["servos"]["tilt"]["max"])
        set_pan_tilt_btn = Button(self.pan_tilt_window, text="Apply",
                                  command=self.apply_pan_tilt)
        set_pan_tilt_btn.grid(row=1, column=0, padx=1, pady=1,
                              sticky=tk.NW + tk.E)
        close_btn = Button(self.pan_tilt_window, text="Close",
                           command=self.pan_tilt_window.close)
        close_btn.grid(row=1, column=1, padx=1, pady=1, sticky=tk.NW + tk.E)
        self.pan_tilt_window.bind("<Escape>",
                                  lambda *args: self.pan_tilt_window.close())
        self.pan_tilt_window.lift()
        self.pan_tilt_window.position = Position(
            x=round(self.position.x + (self.size.width / 2) -
                    (self.pan_tilt_window.size.width / 2)),
            y=round(self.position.y + (self.size.height / 2) -
                    (self.pan_tilt_window.size.height / 2))
        )
        self.pan_tilt_window.update()
        self.new_pan_scale.value = float(
            self.cam.settings["servos"]["pan"]["value"])
        self.pan_tilt_window.grab_set()
        self.pan_tilt_window.grab_focus()
        self.pan_tilt_window.wait_till_destroyed()

    def apply_pan_tilt(self) -> None:
        """
        Apply the pan/tilting.

        :return: None.
        """
        try:
            pan = int(self.new_pan_scale.value)
            tilt = int(self.new_tilt_scale.value)
            self.cam.settings["servos"]["pan"]["value"] = pan
            self.cam.settings["servos"]["tilt"]["value"] = tilt
            if not self.cam.update_settings():
                raise RuntimeError("Failed to update settings!")
        except Exception as e:
            Dialog.show_error(self, title="Remote PiCam: ERROR!",
                              message="There was an error updating the "
                                      "camera pan/tilt!",
                              detail=f"Exception: {e}")
        else:
            Dialog.show_info(self, title="Remote PiCam: Success!",
                             message="Successfully set camera pan/tilt!")

    def set_saturation(self) -> None:
        """
        Set the saturation of the stream.

        :return: None.
        """
        self.saturation_window = CustomDialog(self)
        self.saturation_window.title = "Set the stream saturation"
        self.saturation_window.resizable(False, False)
        for i in range(2):
            self.saturation_window.columnconfigure(i, weight=1)
            self.saturation_window.rowconfigure(i, weight=1)
        new_satur_frame = Frame(self.saturation_window)
        new_satur_frame.grid(row=0, column=0, columnspan=2,
                             sticky=tk.W + tk.E)
        new_satur_lbl = Label(new_satur_frame, text="New saturation: ")
        new_satur_lbl.grid(row=0, column=0, padx=1, pady=1, sticky=tk.NW)
        curr_satur_lbl = Label(new_satur_frame, text="0%")
        curr_satur_lbl.grid(row=0, column=2, padx=1, pady=1, sticky=tk.NE)

        def update_curr_satur_lbl(new_val):
            curr_satur_lbl.text = f"{round(new_val)}%"

        self.new_saturation_scale = Scale(new_satur_frame, length=200,
                                          minimum=-100.0, maximum=100.0,
                                          command=update_curr_satur_lbl)
        self.new_saturation_scale.value = -100
        self.new_saturation_scale.grid(row=0, column=1, padx=1, pady=1,
                                       sticky=tk.NW + tk.E)
        set_satur_btn = Button(self.saturation_window, text="Apply",
                               command=self.apply_saturation)
        set_satur_btn.grid(row=1, column=0, padx=1, pady=1,
                           sticky=tk.NW + tk.E)
        close_btn = Button(self.saturation_window, text="Close",
                           command=self.saturation_window.close)
        close_btn.grid(row=1, column=1, padx=1, pady=1, sticky=tk.NW + tk.E)
        self.saturation_window.bind("<Escape>",
                                    lambda
                                        *args: self.saturation_window.close())
        self.saturation_window.lift()
        self.saturation_window.position = Position(
            x=round(self.position.x + (self.size.width / 2) -
                    (self.saturation_window.size.width / 2)),
            y=round(self.position.y + (self.size.height / 2) -
                    (self.saturation_window.size.height / 2))
        )
        self.saturation_window.update()
        self.new_saturation_scale.value = 0
        self.saturation_window.grab_set()
        self.saturation_window.grab_focus()
        self.saturation_window.wait_till_destroyed()

    def apply_saturation(self) -> None:
        """
        Set the saturation of the PiCam and update it.

        :return: None.
        """
        try:
            saturation = int(self.new_saturation_scale.value)
            self.cam.settings["saturation"]["value"] = saturation
            if not self.cam.update_settings():
                raise RuntimeError("Failed to update settings!")
        except Exception as e:
            Dialog.show_error(self, title="Remote PiCam: ERROR!",
                              message="There was an error updating the "
                                      "stream saturation!",
                              detail=f"Exception: {e}")
        else:
            Dialog.show_info(self, title="Remote PiCam: Success!",
                             message="Successfully set stream saturation!",
                             detail=f"New saturation: "
                                    f"{saturation}%")

    def set_contrast(self) -> None:
        """
        Set the contrast of the stream.

        :return: None.
        """
        self.contrast_window = CustomDialog(self)
        self.contrast_window.title = "Set the stream contrast"
        self.contrast_window.resizable(False, False)
        for i in range(2):
            self.contrast_window.columnconfigure(i, weight=1)
            self.contrast_window.rowconfigure(i, weight=1)
        new_contrast_frame = Frame(self.contrast_window)
        new_contrast_frame.grid(row=0, column=0, columnspan=2,
                                sticky=tk.W + tk.E)
        new_contrast_lbl = Label(new_contrast_frame, text="New contrast: ")
        new_contrast_lbl.grid(row=0, column=0, padx=1, pady=1, sticky=tk.NW)
        curr_contrast_lbl = Label(new_contrast_frame, text="0%")
        curr_contrast_lbl.grid(row=0, column=2, padx=1, pady=1, sticky=tk.NE)

        def update_curr_contrast_lbl(new_val):
            curr_contrast_lbl.text = f"{round(new_val)}%"

        self.new_contrast_scale = Scale(new_contrast_frame, length=200,
                                        minimum=-100.0, maximum=100.0,
                                        command=update_curr_contrast_lbl)
        self.new_contrast_scale.value = -100
        self.new_contrast_scale.grid(row=0, column=1, padx=1, pady=1,
                                     sticky=tk.NW + tk.E)
        set_contrast_btn = Button(self.contrast_window, text="Apply",
                                  command=self.apply_contrast)
        set_contrast_btn.grid(row=1, column=0, padx=1, pady=1,
                              sticky=tk.NW + tk.E)
        close_btn = Button(self.contrast_window, text="Close",
                           command=self.contrast_window.close)
        close_btn.grid(row=1, column=1, padx=1, pady=1, sticky=tk.NW + tk.E)
        self.contrast_window.bind("<Escape>",
                                  lambda *args: self.contrast_window.close())
        self.contrast_window.lift()
        self.contrast_window.position = Position(
            x=round(self.position.x + (self.size.width / 2) -
                    (self.contrast_window.size.width / 2)),
            y=round(self.position.y + (self.size.height / 2) -
                    (self.contrast_window.size.height / 2))
        )
        self.contrast_window.update()
        self.new_contrast_scale.value = 0
        self.contrast_window.grab_set()
        self.contrast_window.grab_focus()
        self.contrast_window.wait_till_destroyed()

    def apply_contrast(self) -> None:
        """
        Set the contrast of the PiCam and update it.

        :return: None.
        """
        try:
            contrast = int(self.new_contrast_scale.value)
            self.cam.settings["contrast"]["value"] = contrast
            if not self.cam.update_settings():
                raise RuntimeError("Failed to update settings!")
        except Exception as e:
            Dialog.show_error(self, title="Remote PiCam: ERROR!",
                              message="There was an error updating the "
                                      "stream contrast!",
                              detail=f"Exception: {e}")
        else:
            Dialog.show_info(self, title="Remote PiCam: Success!",
                             message="Successfully set stream contrast!",
                             detail=f"New contrast: "
                                    f"{contrast}%")

    def set_brightness(self) -> None:
        """
        Set the brightness of the stream.

        :return: None.
        """
        self.bright_window = CustomDialog(self)
        self.bright_window.title = "Set the stream brightness"
        self.bright_window.resizable(False, False)
        for i in range(2):
            self.bright_window.columnconfigure(i, weight=1)
            self.bright_window.rowconfigure(i, weight=1)
        new_bright_frame = Frame(self.bright_window)
        new_bright_frame.grid(row=0, column=0, columnspan=2,
                              sticky=tk.W + tk.E)
        new_bright_lbl = Label(new_bright_frame, text="New brightness: ")
        new_bright_lbl.grid(row=0, column=0, padx=1, pady=1, sticky=tk.NW)
        curr_bright_lbl = Label(new_bright_frame, text="50%")
        curr_bright_lbl.grid(row=0, column=2, padx=1, pady=1, sticky=tk.NE)

        def update_curr_bright_lbl(new_val):
            curr_bright_lbl.text = f"{round(new_val)}%"

        self.new_bright_scale = Scale(new_bright_frame, length=200,
                                      minimum=0.0, maximum=100.0,
                                      command=update_curr_bright_lbl)
        self.new_bright_scale.value = 100
        self.new_bright_scale.grid(row=0, column=1, padx=1, pady=1,
                                   sticky=tk.NW + tk.E)
        set_bright_btn = Button(self.bright_window, text="Apply",
                                command=self.apply_brightness)
        set_bright_btn.grid(row=1, column=0, padx=1, pady=1,
                            sticky=tk.NW + tk.E)
        close_btn = Button(self.bright_window, text="Close",
                           command=self.bright_window.close)
        close_btn.grid(row=1, column=1, padx=1, pady=1, sticky=tk.NW + tk.E)
        self.bright_window.bind("<Escape>",
                                lambda *args: self.bright_window.close())
        self.bright_window.lift()
        self.bright_window.position = Position(
            x=round(self.position.x + (self.size.width / 2) -
                    (self.bright_window.size.width / 2)),
            y=round(self.position.y + (self.size.height / 2) -
                    (self.bright_window.size.height / 2))
        )
        self.bright_window.update()
        self.new_bright_scale.value = 50
        self.bright_window.grab_set()
        self.bright_window.grab_focus()
        self.bright_window.wait_till_destroyed()

    def apply_brightness(self) -> None:
        """
        Set the brightness of the PiCam and update it.

        :return: None.
        """
        try:
            brightness = int(self.new_bright_scale.value)
            self.cam.settings["brightness"]["value"] = brightness
            if not self.cam.update_settings():
                raise RuntimeError("Failed to update settings!")
        except Exception as e:
            Dialog.show_error(self, title="Remote PiCam: ERROR!",
                              message="There was an error updating the "
                                      "stream brightness!",
                              detail=f"Exception: {e}")
        else:
            Dialog.show_info(self, title="Remote PiCam: Success!",
                             message="Successfully set stream brightness!",
                             detail=f"New brightness: "
                                    f"{brightness}%")

    def set_resolution(self) -> None:
        """
        Set the resolution of the stream.

        :return: None.
        """
        self.res_window = CustomDialog(self)
        self.res_window.title = "Set the stream resolution"
        self.res_window.resizable(False, False)
        new_res_frame = Frame(self.res_window)
        new_res_frame.grid(row=0, column=0, columnspan=2)
        new_res_lbl = Label(new_res_frame, text="New resolution: ")
        new_res_lbl.grid(row=0, column=0, padx=1, pady=1, sticky=tk.W)
        resolutions = self.cam.settings["resolution"]["available"]
        self.new_res_combobox = Combobox(new_res_frame, values=resolutions,
                                         width=30)
        self.new_res_combobox.value = resolutions[0]
        self.new_res_combobox.read_only = True
        self.new_res_combobox.grid(row=0, column=1, padx=1, pady=1,
                                   sticky=tk.NW)
        set_res_btn = Button(self.res_window, text="Apply",
                             command=self.apply_resolution)
        set_res_btn.grid(row=1, column=0, padx=1, pady=1, sticky=tk.NW + tk.E)
        close_btn = Button(self.res_window, text="Close",
                           command=self.res_window.close)
        close_btn.grid(row=1, column=1, padx=1, pady=1, sticky=tk.NW + tk.E)
        self.res_window.bind("<Escape>",
                             lambda *args: self.res_window.close())
        self.res_window.lift()
        self.res_window.position = Position(
            x=round(self.position.x + (self.size.width / 2) -
                    (self.res_window.size.width / 2)),
            y=round(self.position.y + (self.size.height / 2) -
                    (self.res_window.size.height / 2))
        )
        self.res_window.grab_set()
        self.res_window.grab_focus()
        self.res_window.wait_till_destroyed()

    def apply_resolution(self) -> None:
        """
        Set the resolution of the PiCam and update it.

        :return: None.
        """
        try:
            resolution = tuple([int(p) for p in
                                self.new_res_combobox.value.split("x")])
            self.cam.settings["resolution"]["selected"] = resolution
            if not self.cam.update_settings():
                raise RuntimeError("Failed to update settings!")
        except Exception as e:
            Dialog.show_error(self, title="Remote PiCam: ERROR!",
                              message="There was an error updating the "
                                      "stream resolution!",
                              detail=f"Exception: {e}")
        else:
            Dialog.show_info(self, title="Remote PiCam: Success!",
                             message="Successfully set stream resolution!",
                             detail=f"New resolution: "
                                    f"{self.new_res_combobox.value}")

    def update_paused_status(self, *args) -> None:
        """
        Update the status bar when we pause or resume the stream.

        :return: None.
        """
        if self.stream_paused_var.get():
            self.status_label.text = "Paused."
        else:
            self.status_label.text = "Resume."

    def update_iso_status(self, *args) -> None:
        """
        Update the status bar when we set the ISO of the stream.

        :return: None.
        """
        try:
            self.cam.settings["iso"]["selected"] = self.iso_var.get()
            if not self.cam.update_settings():
                raise RuntimeError("Failed to update settings!")
        except Exception as e:
            Dialog.show_error(self, title="Remote PiCam: ERROR!",
                              message="There was an error updating the "
                                      "stream ISO!",
                              detail=f"Exception: {e}")
            self.status_label.text = f"Failed to set ISO to " \
                                     f"\"{self.iso_var.get()}\"!"
        else:
            Dialog.show_info(self, title="Remote PiCam: Success!",
                             message="Successfully set ISO!",
                             detail=f"New value: "
                                    f"{self.iso_var.get()}")
            self.status_label.text = f"ISO set to " \
                                     f"\"{self.iso_var.get()}\"!"

    def update_effect_status(self, *args) -> None:
        """
        Update the status bar when we set the image effect of the stream.

        :return: None.
        """
        try:
            self.cam.settings["effect"]["selected"] = self.effect_var.get()
            if not self.cam.update_settings():
                raise RuntimeError("Failed to update settings!")
        except Exception as e:
            Dialog.show_error(self, title="Remote PiCam: ERROR!",
                              message="There was an error updating the "
                                      "stream image effect!",
                              detail=f"Exception: {e}")
            self.status_label.text = f"Failed to set effect to " \
                                     f"\"{self.effect_var.get()}\"!"
        else:
            Dialog.show_info(self, title="Remote PiCam: Success!",
                             message="Successfully set image effect!",
                             detail=f"New value: "
                                    f"{self.effect_var.get()}")
            self.status_label.text = f"Effect set to " \
                                     f"\"{self.effect_var.get()}\"!"

    def update_awb_status(self, *args) -> None:
        """
        Update the status bar when we set the auto white balance of the stream.

        :return: None.
        """
        try:
            self.cam.settings["awb_mode"]["selected"] = self.awb_mode_var.get()
            if not self.cam.update_settings():
                raise RuntimeError("Failed to update settings!")
        except Exception as e:
            Dialog.show_error(self, title="Remote PiCam: ERROR!",
                              message="There was an error updating the "
                                      "stream auto white balance!",
                              detail=f"Exception: {e}")
            self.status_label.text = f"Failed to set auto white balance to " \
                                     f"\"{self.awb_mode_var.get()}\"!"
        else:
            Dialog.show_info(self, title="Remote PiCam: Success!",
                             message="Successfully set auto white balance!",
                             detail=f"New value: "
                                    f"{self.awb_mode_var.get()}")
            self.status_label.text = f"Auto white balance set to " \
                                     f"\"{self.awb_mode_var.get()}\"!"

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
        self.photo_window.bind("<Escape>",
                               lambda *args: self.photo_window.close())
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
        self.conn_window.bind("<Escape>", lambda *args: self.stop_connecting())
        self.conn_window.lift()
        self.conn_window.position = Position(
            x=round(self.position.x + (self.size.width / 2) -
                    (self.conn_window.size.width / 2)),
            y=round(self.position.y + (self.size.height / 2) -
                    (self.conn_window.size.height / 2))
        )
        self.conn_window.grab_set()
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
        logger.debug(f"Attempting to connect to PiCam...")
        self.status_label.text = "Attempting to connect to the PiCam..."
        while not self.cam.connect(timeout=1):
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
                try:
                    image, _ = self.cam.get_image()
                except TypeError:
                    break
                if self.image_queue.full():
                    self.image_queue.get()
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
