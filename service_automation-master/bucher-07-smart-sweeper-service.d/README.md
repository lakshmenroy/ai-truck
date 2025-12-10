 First we need to disable gdm and evict any graphical sessions

### Non persistant way


This wll stop gdm, end the graphics session and launch a pipeline. 

``` 
sudo systemctl stop gdm
sudo loginctl terminate-seat seat0
gst-launch-1.0 filesrc location=demo_prep_video0007_fcd.mp4 ! qtdemux name=demux ! h265parse ! nvv4l2decoder ! nvdrmvideosink -e
```

in this case once you restart the things will come back  to normal as gdm is restarted 

### persistant way 

1. disable the display manager 

```
sudo systemctl disable gdm
```

Note if yu want to re anable gdm run 

```
sudo systemctl enable gdm
```

this folder will include a script to run the example pipeline at boot 


### automate the startup 

to automate the process the script will be called up by a systemms service 

copy the service file to `/etc/systemd/system/`

and then enable the service  (in this case the service name is bucher-custom-video-test-launcher.service) 

```
sudo systemctl enable bucher-custom-video-test-launcher.service
```

NOTE:

remember to unset the DISPLAY env variable if it is set with

```
$unset DISPLAY
```

otherwise the pipelines will fail 




