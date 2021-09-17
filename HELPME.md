# Remote-PiCam-Viewer
View and control a Raspberry Pi Camera mounted on a Waveshare pan/tilt HAT!

## How to use

After launching the program, you should see a window that looks something like
this:

![The Remote PiCam Viewer when you first open it up.](assets/HELPME/1/1.png "Figure 1.1")

To connect to the PiCam, go to `File --> Connect`. 

![The Remote PiCam Viewer with the "File" menu open and the "Connect" command highlighted.](assets/HELPME/1/2.png "Figure 1.2")

You will get a loading screen like this:

![The Remote PiCam Viewer's loading screen when you press "Connect."](assets/HELPME/1/3.png "Figure 1.3")

Now run the Pi's main script. You can press `Cancel` or close that window to 
cancel connecting. 

On success, you will connect to the PiCam and see what the camera sees!

![The Remote PiCam Viewer successfully connected and showing a potted plant.](assets/HELPME/1/4.png "Figure 1.4")

To disconnect, go to `File --> Disconnect` or `File --> Exit`. You can also 
close out of the window, and it will automatically disconnect before exiting. 

![The Remote PiCam Viewer with the "File" menu open and the "Disconnect" command highlighted.](assets/HELPME/1/5.png "Figure 1.5")

## Configuring camera settings

There are a bunch of options to configure in the `Stream` menu:

![The Remote PiCam Viewer with the "Stream" menu open.](assets/HELPME/1/6.png "Figure 1.6")

They should be pretty obvious on what they do. 

## Taking photos

You can take a photo by going to `Stream --> Take photo`. This will bring up a
new window showing buttons on what you want to do with it.

![The Remote PiCam Viewer's photo taken window open.](assets/HELPME/1/7.png "Figure 1.7")

`Show in image viewer` will write the image to a temporary file and try to 
open it in the default image viewer for your platform.

`Save to file` will open a file save dialog so you can save the photo to 
somewhere. Please note that you have to type a supported file extension in the
name otherwise it will error out. 

Please note the photo resolution is determined by the current stream 
resolution.
