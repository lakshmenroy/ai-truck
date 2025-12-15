# SMARTASSIST IMPLEMENTATION GUIDE
---

## PART 1: FUNDAMENTAL CONCEPTS

### What is GStreamer?

**GStreamer** is a multimedia framework for building pipelines that process audio/video streams.

**Think of it like:**
```
UNIX pipes for video:  cat file.txt | grep "error" | wc -l
GStreamer:             camera | resize | encode | save
```

**Key Concepts:**
1. **Elements**: Individual processing blocks (like `cat`, `grep`, `wc`)
2. **Pads**: Connection points (src = output, sink = input)
3. **Bins**: Groups of elements
4. **Pipeline**: The complete processing chain

**Example:**
```python
# Create elements
source = Gst.ElementFactory.make("v4l2src", "camera")  # Video source
convert = Gst.ElementFactory.make("videoconvert", "convert")  # Format converter
sink = Gst.ElementFactory.make("autovideosink", "display")  # Display

# Link them
source.link(convert)
convert.link(sink)

# Run
pipeline.set_state(Gst.State.PLAYING)
```

**In SmartAssist:** We use GStreamer to:
- Capture from 4 cameras
- Process frames through AI
- Encode to H.265
- Stream over network

---

### What is DeepStream?

**DeepStream** is NVIDIA's toolkit for AI video analytics on Jetson/Tesla GPUs.

**What it adds to GStreamer:**
- AI inference elements (`nvinfer`)
- GPU-accelerated processing
- Metadata handling (`nvds...` elements)
- Batch processing for multiple streams

**Key DeepStream Elements:**
```
nvarguscamerasrc → NVIDIA CSI camera source
nvstreammux      → Batches multiple streams for GPU
nvinfer          → Runs TensorRT models
nvvideoconvert   → GPU-accelerated format conversion
nvdsosd          → On-screen display (bounding boxes, text)
```

**Why DeepStream?**
- 10-30x faster than CPU-only processing
- Built for edge devices (Jetson)
- Optimized for real-time video

---

### What is PyDS (Python Bindings)?

**PyDS** lets Python code access DeepStream metadata.

**What is "metadata"?**
```
Video frame:  1920x1080 pixels of image data
Metadata:     { "detections": [{"class": "nozzle", "confidence": 0.95, ...}] }
```

**In SmartAssist:**
```python
import pyds

# Inside a probe function
frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)

# Now we can read AI results:
class_id = obj_meta.class_id
confidence = obj_meta.confidence
bounding_box = obj_meta.rect_params
```

---

## PART 2: STARTUP SEQUENCE (DETAILED)

### Line-by-Line: main.py

```python
#!/usr/bin/env python3
```
**What:** Shebang line
**Why:** Tells OS to run this with Python 3
**When:** Linux/Unix systems use this for executable scripts

---

```python
import sys
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GObject, GLib
```
**What:** Import GStreamer libraries
**Why:** 
- `gi` = GObject Introspection (Python bindings for C libraries)
- `Gst` = GStreamer framework
- `GObject` = Object-oriented framework (threading, signals)
- `GLib` = Low-level utilities (main loop, events)

**How it works:**
- GStreamer is written in C
- `gi` creates Python wrappers
- `require_version('Gst', '1.0')` ensures we use GStreamer 1.0 API

---

```python
Gst.init(None)
```
**What:** Initialize GStreamer
**Why:** MUST be called before any GStreamer operations
**How it works:**
- Registers all GStreamer plugins
- Sets up internal data structures
- Parses command-line arguments (None = no args)

**Without this line:** Program crashes when creating elements

---

```python
app_context = setup_app_context()
```
**What:** Create application context
**Why:** Centralized storage for all configuration and state
**How it works:**
```python
def setup_app_context():
    # Create GStreamer Structure (key-value store)
    app_context = Gst.Structure.new_empty('app_context')
    
    # Load camera config
    config = Config(get_config_path('camera_config.json'))
    
    # Create application context
    actx = AppContext(config)
    actx.initialise_logging()
    
    # Store in structure
    app_context.set_value('app_context_v2', actx)
    
    return app_context
```

**Why use Gst.Structure?**
- Can be passed through GStreamer callbacks
- Thread-safe
- Can store any Python object

---

```python
logger = app_context.get_value('app_context_v2').logger
```
**What:** Get the logger instance
**Why:** All components use same logger for consistent output
**How logging works:**
```python
logger.debug('...')  # Verbose info
logger.info('...')   # Normal info
logger.warning('...') # Warnings
logger.error('...')  # Errors
```

**Output goes to:**
- Console (stdout)
- systemd journal (if running as service)

---

```python
result = initialize_cameras_wrapper(app_context)
```
**What:** Load camera initialization results
**Why:** Camera detection happens in separate service (smartassist-camera-init)
**How it works:**
```python
def initialize_cameras_wrapper(app_context):
    # Find latest camera init results file
    # /tmp/camera_init_results_20251213145030.json
    files = glob.glob('/tmp/camera_init_results_*.json')
    latest = max(files, key=lambda x: extract_datetime(x))
    
    # Load JSON
    with open(latest, 'r') as f:
        init_data = json.load(f)
    
    # Store in app_context
    app_context.set_value('init_config', init_data)
    
    return 0
```

**What's in init_config?**
```json
{
  "cameras": [
    {
      "name": "primary_nozzle",
      "device_path": "/dev/video0",
      "detected_on_init": true,
      "capture_test_passed": true,
      "sensor_mode": 3,
      ...
    }
  ],
  "display_width": 1920,
  "display_height": 1080,
  ...
}
```

---

```python
config = Configuration(get_config_path("logging_config.yaml"))
```
**What:** Load logging configuration
**Why:** Contains CSV column names, output directory, vehicle serial number
**How it works:**
```python
class Configuration:
    def __init__(self, config_file):
        with open(config_file, 'r') as file:
            self.config = yaml.safe_load(file)
    
    def get_can_signals(self):
        return self.config['signal_settings']['can_signals']
    
    def get_serial_number(self):
        return self.config['vehicle_info'][0]['serial_number']
```

**Used for:**
- Creating CSV files with correct columns
- Naming output files with serial number
- Determining what data to log

---

```python
pipeline = build_pipeline(app_context)
```
**What:** Construct the complete GStreamer pipeline
**Why:** This is the heart of the application
**How it works:** (detailed in PART 3 below)

---

```python
bus = pipeline.get_bus()
bus.add_watch(GLib.PRIORITY_DEFAULT, bus_call, loop, pipeline)
```
**What:** Setup message handling
**Why:** Monitor pipeline errors, warnings, state changes
**How it works:**
```python
def bus_call(bus, message, loop, pipeline):
    t = message.type
    
    if t == Gst.MessageType.ERROR:
        err, debug = message.parse_error()
        logger.error(f"Error: {err}, {debug}")
        loop.quit()
    
    elif t == Gst.MessageType.WARNING:
        warn, debug = message.parse_warning()
        logger.warning(f"Warning: {warn}")
    
    elif t == Gst.MessageType.EOS:
        logger.info("End of stream")
        loop.quit()
    
    return True
```

**Why is this needed?**
- GStreamer is asynchronous
- Errors happen in background threads
- Bus provides centralized error reporting

---

```python
start_monitoring_threads(app_context, pipeline)
```
**What:** Start background monitoring
**Why:** Track FPS, monitor CAN override state
**How it works:**
```python
def start_monitoring_threads(app_context, pipeline):
    # Thread 1: FPS monitoring
    fps_thread = threading.Thread(
        target=fps_overlay_thread,
        args=(app_context, pipeline)
    )
    fps_thread.daemon = True
    fps_thread.start()
    
    # Thread 2: Override monitoring
    override_thread = threading.Thread(
        target=override_monitoring,
        args=(app_context,)
    )
    override_thread.daemon = True
    override_thread.start()
```

**What do these threads do?**

**FPS Thread:**
- Reads buffer counts from probes
- Calculates frames per second
- Updates on-screen display

**Override Thread:**
- Listens for CAN message 0x277
- Updates override state
- Changes LED indicators

---

```python
pipeline.set_state(Gst.State.PLAYING)
```
**What:** Start the pipeline
**Why:** Pipelines don't process data until PLAYING state
**How GStreamer states work:**
```
NULL → READY → PAUSED → PLAYING
  ↑      ↑        ↑         ↑
  Init   Ready   Buffered  Running
```

**State transitions:**
- NULL: Pipeline created
- READY: Resources allocated
- PAUSED: Streaming but no processing
- PLAYING: Full speed processing

---

```python
loop = GLib.MainLoop()
loop.run()
```
**What:** Enter main event loop
**Why:** Keep program running, handle events
**How it works:**
- GLib event loop processes:
  - GStreamer bus messages
  - Timer callbacks
  - Signal handlers
  - Network events

**Without this:** Program would exit immediately

---

## PART 3: PIPELINE CONSTRUCTION (DETAILED)

### build_pipeline() Breakdown

```python
def build_pipeline(app_context):
    # Create pipeline container
    pipeline = Gst.Pipeline.new("smartassist-pipeline")
```
**What:** Create the top-level pipeline
**Why:** Pipeline is a special bin that manages timing
**How:** Pipeline = Bin + Clock + Bus

---

```python
    camera_bin = create_multi_argus_camera_bin(app_context)
```
**What:** Create camera source bin
**Why:** 4 cameras need to be captured and muxed together
**How it works:**

#### Inside create_multi_argus_camera_bin():

```python
def create_multi_argus_camera_bin(app_context):
    # Create bin container
    multi_nvargus_bin = Gst.Bin.new('multi_nvargus_bin')
    
    # Create stream muxer
    streammux = Gst.ElementFactory.make("nvstreammux", "mux")
```

**What is nvstreammux?**
- NVIDIA's batching muxer
- Takes N input streams
- Outputs 1 batched stream

**Why batch streams?**
- GPU is parallel processor
- Processing 4 frames together is faster than 1 at a time
- DeepStream inference expects batched input

**Analogy:**
```
Without batching:
  Frame 1 → GPU → Result 1
  Frame 2 → GPU → Result 2
  Frame 3 → GPU → Result 3
  Frame 4 → GPU → Result 4
  Time: 40ms

With batching:
  [Frame 1, 2, 3, 4] → GPU → [Result 1, 2, 3, 4]
  Time: 15ms (parallel processing!)
```

---

```python
    # Configure muxer
    streammux.set_property('batch-size', 4)  # 4 cameras
    streammux.set_property('width', 960)     # Resize each stream
    streammux.set_property('height', 540)
    streammux.set_property('batched-push-timeout', 4000000)  # 4ms timeout
    streammux.set_property('live-source', 1)  # Real-time source
```

**What each property means:**

**batch-size=4:**
- "Combine 4 input streams"
- Output tensor shape: [4, 540, 960, 3]

**width/height:**
- "Resize each stream to 960x540"
- Why? AI models expect fixed size
- Original: 1920x1080 → Resized: 960x540 (half size)

**batched-push-timeout:**
- "If we don't have all 4 frames, wait max 4ms then push anyway"
- Prevents one slow camera from blocking others

**live-source=1:**
- "This is real-time data, don't buffer excessively"
- Minimizes latency

---

```python
    for i, camera in enumerate(cameras):
        # Create camera source
        source = make_argus_camera_source(sensor_id, camera_config)
```

**What is make_argus_camera_source()?**

```python
def make_argus_camera_source(sensor_id, camera_config):
    # Create NVIDIA Argus camera source
    source = Gst.ElementFactory.make('nvarguscamerasrc', f'camera_{sensor_id}')
    
    # Configure
    source.set_property('sensor-id', sensor_id)  # Which camera (0-7)
    source.set_property('sensor-mode', 3)        # Resolution mode
    source.set_property('gainrange', '1.0 8.0')  # Auto-gain range
    source.set_property('exposuretimerange', '20000 336980000')  # Auto-exposure
    
    return source
```

**What is nvarguscamerasrc?**
- NVIDIA's CSI camera capture element
- Uses Argus API (low-level camera control)
- Hardware-accelerated

**What is sensor-id?**
- Jetson has 8 CSI lanes (0-7)
- Each camera connects to one lane
- sensor-id tells which lane to use

**What is sensor-mode?**
```
Mode 0: 3840x2160 @ 30fps (4K)
Mode 1: 1920x1080 @ 60fps (HD, high FPS)
Mode 2: 1280x720  @ 120fps (HD, very high FPS)
Mode 3: 1920x1080 @ 30fps (HD, balanced) ← WE USE THIS
```
**Why mode 3?**
- Good resolution (1080p)
- Good frame rate (30 FPS)
- Lower bandwidth than 4K

**What is gainrange?**
- Auto-gain range: 1.0x to 8.0x
- Brightens image in low light
- Like ISO on a camera

**What is exposuretimerange?**
- Microseconds: 20,000μs to 336,980,000μs
- 0.02ms to 337ms exposure time
- Controls how long sensor captures light

---

```python
        # Create converter
        convert = Gst.ElementFactory.make('nvvideoconvert', f'convert_{i}')
        
        # Create tee (3-way splitter)
        tee = Gst.ElementFactory.make('tee', f'tee_{i}')
```

**What is nvvideoconvert?**
- GPU-accelerated format converter
- Can resize, rotate, crop, color-convert

**Why do we need it?**
- Camera outputs: NV12 format (YUV)
- AI models need: RGB format
- Converter does: NV12 → RGBA

**What is tee?**
- Splits one stream into multiple copies
- Like a T-shaped pipe connector

**Why split?**
```
Camera →convert→tee─┬→ HR recording (1920x1080)
                    ├→ AI inference (960x540)
                    └→ UDP streaming (1920x1080)
```

Each branch gets a copy of the stream!

---

### Inference Bin Construction

```python
    inference_bin = create_bucher_inference_bin(app_context)
```

#### Inside create_bucher_inference_bin():

```python
def create_bucher_inference_bin(app_context):
    # Create nozzlenet bin
    nozzle_bin = create_nozzlenet_inference_bin(app_context, config_paths)
    
    # Create CSI bin
    csi_bin = create_csiprobebin(app_context, config_paths)
    
    # Combine with metamux
    metamux = Gst.ElementFactory.make('nvdsmetamux', 'metamux')
```

**What is nvdsmetamux?**
- Combines metadata from multiple sources
- Each camera/model adds metadata
- Metamux merges it all

**Why?**
```
Camera 0 → Nozzle inference → {nozzle_state: "clear"}
Camera 1 → CSI computation  → {csi_score: 0.85}

Metamux → {cam0: {nozzle: "clear"}, cam1: {csi: 0.85}}
```

---

### Nozzlenet Inference Bin

```python
def create_nozzlenet_inference_bin(app_context, config_paths):
    # Preprocessing
    preprocess = Gst.ElementFactory.make('nvdspreprocess', 'nozzle_preprocess')
    
    # AI inference
    pgie = Gst.ElementFactory.make('nvinfer', 'nozzlenet-infer')
    
    # Queue
    queue = Gst.ElementFactory.make('queue', 'nozzle_queue')
```

**What is nvdspreprocess?**
- Prepares frames for AI model
- Mean subtraction
- Normalization
- ROI cropping

**Why?**
- AI models trained on normalized data: [0, 1] range
- Raw camera: [0, 255] range
- Preprocess converts: `pixel / 255.0`

**What is nvinfer?**
- **THE CORE AI ENGINE**
- Runs TensorRT models on GPU
- Outputs: bounding boxes, classes, confidences

**How nvinfer works:**

1. **Reads config file:**
```
[property]
gpu-id=0
net-scale-factor=0.0039215697906911373  # 1/255
model-file=/path/to/model.plan
labelfile-path=/path/to/labels.txt
```

2. **Loads TensorRT engine:**
- `.plan` file = optimized GPU model
- Created from ONNX/UFF using `trtexec`

3. **For each batch:**
- Input: 4 frames [4, 540, 960, 3]
- Output: Detections [N, 6] where each row is:
  ```
  [batch_id, class_id, confidence, x, y, width, height]
  ```

4. **Adds to metadata:**
```python
frame.obj_meta_list → [
    {class_id: 1, confidence: 0.95, rect: {x:100, y:200, w:50, h:60}},
    {class_id: 3, confidence: 0.88, rect: {x:300, y:400, w:45, h:55}},
]
```

---

### Probe Functions (WHERE MAGIC HAPPENS)

```python
    # Attach probe to nvinfer output
    nvinfer_src_pad = pgie.get_static_pad('src')
    nvinfer_src_pad.add_probe(
        Gst.PadProbeType.BUFFER,
        nozzlenet_src_pad_buffer_probe,
        app_context
    )
```

**What is a probe?**
- Callback function called for every buffer
- Like a tap in a water pipe
- Can inspect/modify data flowing through

**When is probe called?**
```
Frame→nvinfer→[PROBE CALLED HERE]→queue
             ↑
        Every frame!
```

**What happens in nozzlenet_src_pad_buffer_probe()?**

```python
def nozzlenet_src_pad_buffer_probe(pad, info, u_data):
    # Get buffer
    gst_buffer = info.get_buffer()
    
    # Get batch metadata
    batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
    
    # Iterate frames in batch
    l_frame = batch_meta.frame_meta_list
    while l_frame:
        frame_meta = pyds.NvDsFrameMeta.cast(l_frame.data)
        
        # Iterate objects detected in this frame
        l_obj = frame_meta.obj_meta_list
        while l_obj:
            obj_meta = pyds.NvDsObjectMeta.cast(l_obj.data)
            
            # Extract detection info
            class_id = obj_meta.class_id
            confidence = obj_meta.confidence
            bbox = obj_meta.rect_params
            
            # *** THIS IS WHERE WE PROCESS AI RESULTS ***
            if class_id == 1:  # Action object detected
                state_machine.update_state("BLOCKED")
                fan_speed = state_machine.get_fan_speed()
                
                # Send to CAN
                can_client.send_nozzle_state(state, fan_speed)
            
            l_obj = l_obj.next
        
        l_frame = l_frame.next
    
    return Gst.PadProbeReturn.OK
```

**Line-by-line:**

**pyds.gst_buffer_get_nvds_batch_meta()**
- Extracts DeepStream metadata from GStreamer buffer
- Returns NvDsBatchMeta object

**batch_meta.frame_meta_list**
- List of frames in this batch (4 cameras = 4 frames)
- Linked list structure

**NvDsFrameMeta.cast(l_frame.data)**
- Cast generic pointer to frame metadata
- Now we can access frame properties

**frame_meta.obj_meta_list**
- List of detected objects in this frame
- Each object = one detection

**NvDsObjectMeta.cast(l_obj.data)**
- Cast to object metadata
- Contains class, confidence, bounding box

**class_id, confidence, rect_params**
```
class_id:     Which class? (0=bg, 1=action, 2=empty, 3=check, 4=gravel)
confidence:   How sure? (0.0 to 1.0)
rect_params:  Where? {left, top, width, height}
```

**state_machine.update_state()**
- Updates nozzle state machine
- Logic:
  ```
  Current state: CLEAR
  Detection: BLOCKED object
  New state: BLOCKED
  Fan speed: 80%
  ```

**can_client.send_nozzle_state()**
- Formats CAN message
- Sends via socket to CAN server
- CAN server broadcasts on bus

---

## CSI Computation (Detailed)

```python
def compute_csi_buffer_probe(pad, info, u_data):
    # Get road segmentation mask
    road_mask = extract_segmentation(obj_meta, ROAD_UNIQUE_ID)
    
    # Get garbage segmentation mask
    garbage_mask = extract_segmentation(obj_meta, GARBAGE_UNIQUE_ID)
    
    # Compute CSI
    csi_value = compute_csi(road_mask, garbage_mask, camera_name)
```

**What is road_mask?**
- Binary mask: 1 = road, 0 = not road
- Shape: [540, 960]
- Generated by segmentation model

**How is it computed?**

```python
def compute_csi(road_mask, garbage_mask, camera_name):
    # 1. Apply trapezoid filter
    trapezoid = get_trapezoid_mask(camera_name)
    road_roi = road_mask * trapezoid  # Element-wise multiply
    garbage_roi = garbage_mask * trapezoid
    
    # 2. Compute areas
    road_area = np.sum(road_roi)  # Count road pixels
    garbage_area = np.sum(garbage_roi)  # Count garbage pixels
    
    # 3. Compute dirty percentage
    if road_area > 0:
        dirty_ratio = garbage_area / road_area
    else:
        dirty_ratio = 0.0
    
    # 4. Convert to CSI (0-100 scale)
    csi = (1 - dirty_ratio) * 100
    csi = np.clip(csi, 0, 100)
    
    # 5. Discretize to levels
    csi_discrete = discretize_csi(csi, levels=21)  # Front: 21 levels
    
    return csi_discrete
```

**Why trapezoid?**
```
Full image:        Trapezoid ROI:
┌────────────┐    ┌────────────┐
│            │    │ \        / │ ← Top
│   ROAD     │ →  │  \      /  │ ← Focus on road
│            │    │   ROAD /   │   (ignore sky, sides)
└────────────┘    └──────────┘ ← Bottom (full width)
```

**Why discretize?**
- Smooth value: 73.456%
- Discretized: 73.3% (one of 21 levels)
- Reduces noise, makes CSV cleaner

---

## Output Bins

### HR Output Bin

```python
def create_hr_output_bin(app_context):
    # Converter
    nvvidconv = Gst.ElementFactory.make('nvvideoconvert', 'hr_convert')
    
    # Caps filter (set output format)
    caps = Gst.ElementFactory.make('capsfilter', 'hr_caps')
    caps.set_property('caps', Gst.Caps.from_string(
        'video/x-raw(memory:NVMM), format=I420'
    ))
    
    # Encoder
    encoder = Gst.ElementFactory.make('nvv4l2h265enc', 'hr_encoder')
    encoder.set_property('bitrate', 4000000)  # 4 Mbps
    
    # Parser
    parser = Gst.ElementFactory.make('h265parse', 'hr_parse')
    
    # File sink
    filesink = Gst.ElementFactory.make('splitmuxsink', 'hr_filesink')
    filesink.set_property('location', '/mnt/ssd/videos/video_%05d.mp4')
    filesink.set_property('max-size-time', 1200000000000)  # 20 min files
```

**What is nvv4l2h265enc?**
- Hardware H.265 (HEVC) encoder
- Uses Jetson video encoder (not CPU)
- Much faster than software encoding

**Why H.265?**
- Better compression than H.264
- 4 Mbps for 1080p (vs 8 Mbps for H.264)
- Smaller files, same quality

**What is splitmuxsink?**
- Splits video into time-based segments
- max-size-time = 1200 seconds = 20 minutes
- Creates: `video_00001.mp4`, `video_00002.mp4`, etc.

**Why split?**
- Easier to manage
- Can delete old segments
- If recording crashes, only lose 20 minutes

---

## SUMMARY OF DATA FLOW

```
CAMERA 0 (primary_nozzle)
  ↓ [raw NV12 frames, 1920x1080 @ 30fps]
nvarguscamerasrc
  ↓ [sensor data]
nvvideoconvert
  ↓ [RGBA format]
tee (3-way split)
  ├─→ HR OUTPUT
  │     ↓ [1920x1080]
  │   nvv4l2h265enc
  │     ↓ [H.265 compressed]
  │   splitmuxsink → /mnt/ssd/videos/video_00001.mp4
  │
  ├─→ INFERENCE PATH
  │     ↓ [960x540 resized]
  │   nvstreammux (batch with other cameras)
  │     ↓ [batch of 4 frames]
  │   nvinfer (TensorRT model)
  │     ↓ [metadata: detections]
  │   PROBE → state_machine → CAN message → Socket → can-server → CAN bus
  │     ↓
  │   nvdsmetamux
  │     ↓
  │   nvdsosd (draw boxes)
  │     ↓
  │  nvv4l2h265enc
  │     ↓
  │   udpsink → Network stream
  │
  └─→ (Same for cameras 1, 2, 3)
```

---

## TOOLS SUMMARY

| Tool | Purpose | Why We Need It |
|------|---------|----------------|
| **GStreamer** | Multimedia framework | Process video streams |
| **DeepStream** | AI video toolkit | GPU-accelerated inference |
| **PyDS** | Python bindings | Access metadata in Python |
| **nvarguscamerasrc** | Camera capture | Read CSI cameras |
| **nvstreammux** | Stream batcher | Combine 4 cameras for GPU |
| **nvinfer** | AI inference | Run TensorRT models |
| **nvv4l2h265enc** | Video encoder | Compress to H.265 |
| **nvdsosd** | On-screen display | Draw bounding boxes |
| **splitmuxsink** | File splitting | Create time-based segments |

---

## NEXT: PART 4 (if you need more detail)

I can continue with:
1. CAN communication detailed walkthrough
2. State machine logic detailed explanation
3. CSV logging detailed walkthrough
4. Service startup sequence detailed explanation
5. Systemd integration detailed explanation

Just let me know which area you want me to explain next!