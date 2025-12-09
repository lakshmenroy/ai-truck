#export LD_PRELOAD=/home/ganindu/.pyenv/versions/3.8.10/envs/PY38-TEST/lib/python3.8/site-packages/sklearn/__check_build/../../scikit_learn.libs/libgomp-d22c30c5.so.1.0.0

import sys

from torch2trt import get_arg
sys.path.append("./mw_csi_pkg/csi")

import torch
# from torch import nn
# from torch.utils.data import DataLoader
# from torchvision import datasets
# from torchvision.transforms import ToTensor

import tensorrt as trt
from torch2trt import torch2trt
from torch2trt import tensorrt_converter


# from csi_utils import get_weight_matrix_linspace

from mw_csi_pkg.csi.csi_utils import compute_csi
from mw_csi_pkg.csi.csi_utils import get_discrete_csi
# from mw_csi_pkg.csi.csi_utils import compute_failure_mode
# from mw_csi_pkg.utils.main_utils import convert_tensors_to_numpy_arrays

import gi
import logging
import cv2 as cv
import numpy as np

gi.require_version("Gst", "1.0")
gi.require_version("GstBase", "1.0")

from gi.repository import Gst
from gi.repository import GLib
from gi.repository import GstBase
from gi.repository import GObject

import yaml
from matplotlib.colors import ListedColormap

from mw_csi_pkg.inference.inference import Inference
# from mw_csi_pkg.visualization.plotting_utils import put_csi_text
# from mw_csi_pkg.visualization.plotting_utils import blended_road_pred
# from mw_csi_pkg.visualization.plotting_utils import put_failure_mode_text
# from mw_csi_pkg.visualization.plotting_utils import blended_garbage_and_road
# from mw_csi_pkg.visualization.plotting_utils import blended_failure_mode_colored
# from mw_csi_pkg.visualization.plotting_utils import blend_failure_mode_and_street
'''
@tensorrt_converter('torch.nn.functional.hardtanh')
def convert_hardtanh(ctx):
    input = get_arg(ctx, 'input', pos=0, default=None)
    min_val = get_arg(ctx, 'min_val', pos=1, default=-1.0)
    max_val = get_arg(ctx, 'max_val', pos=2, default=1.0)
    output = ctx.method_return
    
    layer = ctx.network.add_activation(input._trt, trt.ActivationType.CLIP)
    layer.alpha = min_val
    layer.beta = max_val
    
    output._trt = layer.get_output(0)
'''
# load configurations from YAML file
CONFIG_FILE = "./config/csi_config.yaml"
with open(CONFIG_FILE, "r") as stream:
    config = yaml.safe_load(stream)

# define colors for each label
class_labels = config["GARBAGE_MODEL"]["CLASS_LABELS"]
colors = [[68, 1, 84], [32, 144, 140], [253, 231, 36]]
label_colors = {k: v for k, (v, _) in enumerate(zip(colors, class_labels))}

# create a colormap using the defined colors
cmap = ListedColormap([np.array(color) / 255.0 for color in label_colors.values()])

base_garbage_model_path = "/mnt/ssd/csi_pipeline/mw_project/training_suite/checkpoints/base_models/mw_garbage_checkpoint.pt"
base_road_model_path = "/mnt/ssd/csi_pipeline/mw_project/training_suite/checkpoints/base_models/mw_road_checkpoint.pt"

# creating an inference object
inference = Inference(config)

# perform inference on the input image
camera = "front"
image_path = "./test_images/4.png"
bgr_image = cv.imread(image_path)

road_model = inference.road_model
garbage_model = inference.garbage_model

device = inference.device
print(f"Using device: {device}")

krn_size = 3
kernel = torch.zeros(size=(1, 1, krn_size, krn_size), dtype=torch.float32, requires_grad=False)
kernel[:, :, (krn_size // 2) + 1, (krn_size // 2) + 1] = 1.
if torch.cuda.is_available():
    kernel = kernel.cuda()


def make_sample_input_for_trt():
    # Create a sample input: a numpy array with shape (1820, 1920, 3) with float values
    sample_input = np.ones((1080, 1920, 3), dtype=np.float32)
    sample_input_processed = inference.transform(sample_input).unsqueeze(0).to(device)
    return sample_input_processed

frame = cv.cvtColor(src=cv.imread(image_path), code=cv.COLOR_BGR2RGB)
frame = frame.astype(dtype=np.float32) / 255.0
frame_t = inference.transform(frame).unsqueeze(0).to(device)

# perform inference on the input image
road_model_cuda = road_model.eval().cuda()
garbage_model_cuda = garbage_model.eval().cuda()

road_model_sample_input = make_sample_input_for_trt()
road_model_trt = torch2trt(road_model_cuda, [road_model_sample_input], fp16_mode=True)

garbage_model_sample_input = make_sample_input_for_trt()
garbage_model_trt = torch2trt(garbage_model_cuda, [garbage_model_sample_input], fp16_mode=True)

torch.save(road_model_trt.state_dict(), "models/csi-orin/road_model_trt.pth")
torch.save(garbage_model_trt.state_dict(), "models/csi-orin/garbage_model_trt.pth")