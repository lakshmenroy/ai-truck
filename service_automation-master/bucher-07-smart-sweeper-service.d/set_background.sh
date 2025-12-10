#!/bin/bash

#gst-launch-1.0 playbin uri=file:///mnt/ssd/media/logos/logo_loop.mp4 video-sink=nvdrmvideosink
#sudo fbi -T 1 -d /dev/fb0 /mnt/ssd/media/logos/BUC_MUN_Logo_RGB_LAn920x1080_Black_BG_rev_2.png
# no verbose mode (with nothing on)
#sudo dd if=/dev/zero of=/dev/fb0
# frame buffer image viewer method
#sudo fbi -T 1 -d /dev/fb0 -noverbose /mnt/ssd/media/logos/BUC_MUN_Logo_RGB_LAn1920x1080_Black_BG_rev_2_cropped.png



#note to convert the pmg to a raw image for the framebuffer (image should be right format otherwise pixels will be shifted)
#convert BUC_MUN_Logo_RGB_LAn1920x1080_Black_BG_rev_2_cropped.png -depth 8 rgba:BUC_MUN_Logo_RGB_LAn1920x1080_Black_BG_rev_2_cropped.raw
#sudo dd if=/mnt/ssd/media/logos/BUC_MUN_Logo_RGB_LAn1920x1080_Black_BG_rev_2_cropped.raw of=/dev/fb0
/usr/bin/sudo dd if=/mnt/ssd/media/logos/BUC_MUN_Logo_RGB_LAn1920x1080_Black_BG_rev_2_cropped.raw of=/dev/fb0 &> /dev/null
