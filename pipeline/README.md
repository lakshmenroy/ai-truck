# Note

Make sure other video services are not running 

make sure CAN is working or disabled 

run `csi_pipeline_demo_syslogic.py`  


check bashrc for environment setup that may help ethe code work 

Note the pyenv environment used in this folder 

do not run other files as they are not setup yet (9/4/2024)

you need torch2trt (https://github.com/NVIDIA-AI-IOT/torch2trt)

sudo apt-get install libopenblas-base libopenmpi-dev libomp-dev

to install deepstream NV Plugins 

```
cd /opt/nvidia/deepstream/deepstream
./install.sh
```

this si needed to install the plugin

```
sudo apt install libgstrtspserver-1.0-dev
```