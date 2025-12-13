# 📚 SmartAssist Pipeline Execution Flow

Complete flowchart showing function calls, execution order, and file locations.

---

## 🎯 Main Execution Sequence

### Application Startup

START: python3 /opt/smartassist/pipeline/src/main.py

  ↓

[1] Gst.init()
    Location: pipeline/src/main.py:line 45
    
  ↓

[2] setup_app_context()
    Location: pipeline/src/context.py:setup_app_context()
    
      ↓
    
    [2.1] Config.__init__()
          Location: pipeline/src/context.py:Config.__init__()
          Action: Load camera_config.json
          
      ↓
    
    [2.2] AppContext.__init__()
          Location: pipeline/src/context.py:AppContext.__init__()
          
      ↓
    
    [2.3] AppContext.initialise_logging()
          Location: pipeline/src/context.py:AppContext.initialise_logging()
          
  ↓

[3] initialize_cameras_wrapper()
    Location: pipeline/src/main.py:initialize_cameras_wrapper()
    
      ↓
    
    [3.1] load_latest_init_status()
          Location: pipeline/src/utils/systemd.py:load_latest_init_status()
          Action: Read /tmp/camera_init_results_*.json
          
  ↓

[4] Configuration()
    Location: pipeline/src/utils/config.py:Configuration
    Action: Load logging_config.yaml
    
  ↓

[5] build_pipeline()
    Location: pipeline/src/pipeline/builder.py:build_pipeline()
    
      ├─→ [5.1] create_multi_argus_camera_bin()
      │         Location: pipeline/src/pipeline/builder.py
      │         Creates: 4x nvarguscamerasrc + converters + tee
      │
      ├─→ [5.2] create_bucher_inference_bin()
      │         Location: pipeline/src/pipeline/bins.py
      │         
      │           ├─→ [5.2.1] create_nozzlenet_inference_bin()
      │           │           Location: models/nozzlenet/src/bins.py
      │           │           
      │           │             └─→ [5.2.1.1] Attach probe
      │           │                           nozzlenet_src_pad_buffer_probe()
      │           │                           Location: models/nozzlenet/src/probes.py
      │           │
      │           └─→ [5.2.2] create_csiprobebin()
      │                       Location: models/csi/src/bins.py
      │                       
      │                         └─→ [5.2.2.1] Attach probe
      │                                       compute_csi_buffer_probe()
      │                                       Location: models/csi/src/probes.py
      │
      ├─→ [5.3] create_hr_output_bin()
      │         Location: pipeline/src/pipeline/bins.py
      │         Creates: H.265 encoder + file sink
      │
      └─→ [5.4] create_udpsinkbin()
                Location: pipeline/src/pipeline/bins.py
                Creates: H.265 encoder + UDP sink
    
  ↓

[6] Setup bus watch
    Location: pipeline/src/main.py:bus_call()
    Action: Monitor GStreamer bus messages
    
  ↓

[7] start_monitoring_threads()
    Location: pipeline/src/monitoring/threads.py
    
      ├─→ [7.1] fps_overlay_thread()
      │         Location: pipeline/src/monitoring/threads.py:fps_overlay_thread()
      │         Action: Monitor and display FPS
      │
      └─→ [7.2] override_monitoring()
                Location: pipeline/src/monitoring/threads.py:override_monitoring()
                Action: Monitor CAN override state
    
  ↓

[8] pipeline.set_state(Gst.State.PLAYING)
    Location: pipeline/src/main.py
    Action: Start pipeline
    
  ↓

[9] GLib.MainLoop().run()
    Location: pipeline/src/main.py
    Action: Enter main event loop

  ↓

[RUNTIME PROCESSING - See section below]


---

## 🔄 Runtime Data Flow

### Camera Buffer Processing


CAMERA BUFFER ARRIVES
  ↓
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ GStreamer Pipeline (Running)                                                │
│                                                                             │
│  nvarguscamerasrc → nvvidconv → tee (3-way split)                           │
│                                                                             │
│    ├─→ Queue → HR Output Bin                                                │
│    │            (H.265 recording)                                           │
│    │                                                                        │
│    ├─→ Queue → nvstreamdemux → Per-camera streams                           │
│    │                                                                        │
│    │            ├─→ Nozzle Cameras (primary/secondary)                      │
│    │            │   ↓                                                       │
│    │            │   nvstreammux (videomux)                                  │
│    │            │   ↓                                                       │
│    │            │   nvinfer (nozzlenet model)                               │
│    │            │   ↓                                                       │
│    │            │   PROBE: nozzlenet_src_pad_buffer_probe()                 │
│    │            │         Location: models/nozzlenet/src/probes.py:30       |
│    │            │         ↓                                                 │
│    │            │         Extract metadata                                  │
│    │            │         ↓                                                 │
│    │            │         Iterate detected objects                          │
│    │            │         ↓                                                 │
│    │            │         Filter by class_id                                │
│    │            │         ↓                                                 │
│    │            │         Update SmartStateMachine                          │
│    │            │         Location: models/nozzlenet/src/state_machine.py   │
│    │            │         ↓                                                 │
│    │            │         state_machine.status_send()                       │
│    │            │         ↓                                                 │
│    │            │         Calculate fan_speed                               │
│    │            │         ↓                                                 │
│    │            │         CANClient.update_can_bytes()                      │
│    │            │         Location: pipeline/src/can/client.py:150          │
│    │            │         ↓                                                 │
│    │            │         Send to CAN server socket                         │
│    │            │         ↓                                                 │
│    │            │         Add OSD metadata                                  │
│    │            │                                                           │
│    │            └─→ CSI Cameras (front/rear)                                │
│    │                ↓                                                       │
│    │                nvstreammux (csi_merger)                                │
│    │                ↓                                                       │
│    │                nvinfer (road segmentation)                             │
│    │                +                                                       │
│    │                nvinfer (garbage segmentation)                          │
│    │                ↓                                                       │
│    │                PROBE: compute_csi_buffer_probe()                       │
│    │                      Location: models/csi/src/probes.py:30             │
│    │                      ↓                                                 │
│    │                      Extract road mask                                 │
│    │                      Location: probes.py:85                            │
│    │                      ↓                                                 │
│    │                      Extract garbage mask                              │
│    │                      Location: probes.py:110                           │
│    │                      ↓                                                 │
│    │                      compute_csi()                                     │
│    │                      Location: models/csi/src/computation.py:80        │
│    │                        ↓                                               │
│    │                        create_filtering_masks()                        │
│    │                        Location: computation.py:20                     │
│    │                        ↓                                               │
│    │                        compute_road_area()                             │
│    │                        Location: computation.py:150                    │
│    │                        ↓                                               │
│    │                        compute_garbage_area()                          │
│    │                        Location: computation.py:180                    │
│    │                        ↓                                               │
│    │                        get_discrete_csi()                              │
│    │                        Location: computation.py:200                    │
│    │                      ↓                                                 │
│    │                      Write CSV log                                     │
│    │                      Location: probes.py:180                           │
│    │                                                                        │
│    └─→ Queue → nvdsmetamux → Aggregated metadata                            │
│                ↓                                                            │
│                nvvideoconvert                                               │
│                ↓                                                            │
│                nvmultistreamtiler (4-way tile)                              │
│                ↓                                                            │
│                nvosd (On-Screen Display)                                    │
│                ↓                                                            │
│                UDP Sink Bin (H.265 encode + UDP)                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```
---

## 📊 Function Call Stack Examples

### Example 1: Nozzle Detection Processing

**When nozzle camera buffer arrives:**

```
1. GStreamer calls probe callback
   nozzlenet_src_pad_buffer_probe(pad, info, user_data)
   Location: models/nozzlenet/src/probes.py:30
   
2. Get batch metadata
   batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
   Location: models/nozzlenet/src/probes.py:65
   
3. Iterate frames
   for frame_meta in batch_meta.frame_meta_list:
   Location: models/nozzlenet/src/probes.py:75
   
4. Iterate objects
   for obj_meta in frame_meta.obj_meta_list:
   Location: models/nozzlenet/src/probes.py:95
   
5. Check detection class
   if obj_meta.class_id == PGIE_CLASS_ID_NOZZLE_CLEAR:
   Location: models/nozzlenet/src/probes.py:120
   Constants: models/nozzlenet/src/constants.py
   
6. Update state machine
   state_machine.status_send(nozzle_state, fan_speed)
   Location: models/nozzlenet/src/state_machine.py:80
   
7. Get fan speed
   fan_speed = state_machine.fan_speed
   Location: models/nozzlenet/src/state_machine.py:200 (property)
   
8. Update CAN bytes
   can_client.update_can_bytes(nozzle_state, fan_speed)
   Location: pipeline/src/can/client.py:150
   
9. Send to CAN server
   can_client.send_data()
   Location: pipeline/src/can/client.py:100
   Socket: /tmp/can_server.sock
   
10. Add display metadata
    display_meta = pyds.nvds_acquire_display_meta_from_pool(batch_meta)
    Location: models/nozzlenet/src/probes.py:180
    
11. Return probe result
    return Gst.PadProbeReturn.OK
    Location: models/nozzlenet/src/probes.py:250
```

### Example 2: CSI Computation

**When CSI camera buffer arrives:**

```
1. GStreamer calls probe callback
   compute_csi_buffer_probe(pad, info, user_data)
   Location: models/csi/src/probes.py:30
   
2. Get batch metadata
   batch_meta = pyds.gst_buffer_get_nvds_batch_meta(hash(gst_buffer))
   Location: models/csi/src/probes.py:60
   
3. Iterate frames
   for frame_meta in batch_meta.frame_meta_list:
   Location: models/csi/src/probes.py:70
   
4. Extract road segmentation
   # From road inference metadata
   road_mask = extract_segmentation_mask(frame_meta, "road")
   Location: models/csi/src/probes.py:85
   
5. Extract garbage segmentation
   # From garbage inference metadata
   garbage_mask = extract_segmentation_mask(frame_meta, "garbage")
   Location: models/csi/src/probes.py:110
   
6. Compute CSI
   csi_result = compute_csi(road_mask, garbage_mask, frame_meta)
   Location: models/csi/src/computation.py:80
   
     6.1. Create filtering masks
          masks = create_filtering_masks(frame_height, frame_width)
          Location: models/csi/src/computation.py:20
          Action: Create trapezoid ROI masks
   
     6.2. Compute road area
          road_area = compute_road_area(road_mask, masks)
          Location: models/csi/src/computation.py:150
          Action: Count road pixels in ROI
   
     6.3. Compute garbage area
          garbage_area = compute_garbage_area(garbage_mask, masks)
          Location: models/csi/src/computation.py:180
          Action: Count garbage pixels in ROI
   
     6.4. Calculate CSI score
          csi_score = (road_area - garbage_area) / total_area * 100
          Location: models/csi/src/computation.py:195
   
     6.5. Get discrete level
          discrete_csi = get_discrete_csi(csi_score)
          Location: models/csi/src/computation.py:200
          Returns: A, B, C, or D
   
7. Write to CSV
   csv_writer.writerow([timestamp, csi_score, discrete_csi, ...])
   Location: models/csi/src/probes.py:180
   
8. Return probe result
   return Gst.PadProbeReturn.OK
   Location: models/csi/src/probes.py:200
```
### Example 3: Pipeline Initialization

**From startup to PLAYING state:**

```
1. Python interpreter starts
   python3 /opt/smartassist/pipeline/src/main.py
   
2. Import modules
   from context import setup_app_context
   from pipeline.builder import build_pipeline
   from monitoring.threads import start_monitoring_threads
   Location: main.py:1-30
   
3. Initialize GStreamer
   Gst.init(None)
   Location: main.py:45
   
4. Setup application context
   app_context = setup_app_context()
   Location: context.py:setup_app_context()
   
     4.1. Create Config object
          config = Config()
          Location: context.py:Config.__init__()
          Loads: pipeline/config/camera_config.json
   
     4.2. Create AppContext object
          app_context = AppContext(config)
          Location: context.py:AppContext.__init__()
   
     4.3. Initialize logging
          app_context.initialise_logging()
          Location: context.py:AppContext.initialise_logging()
          Loads: pipeline/config/logging_config.yaml
   
5. Load camera initialization status
   initialize_cameras_wrapper(app_context)
   Location: main.py:initialize_cameras_wrapper()
   
     5.1. Call systemd utility
          load_latest_init_status(app_context=app_context)
          Location: utils/systemd.py:load_latest_init_status()
          Reads: /tmp/camera_init_results_*.json
   
6. Build GStreamer pipeline
   pipeline = build_pipeline(app_context)
   Location: pipeline/builder.py:build_pipeline()
   
     6.1. Create camera source bin
          camera_bin = create_multi_argus_camera_bin(app_context)
          Location: pipeline/builder.py:create_multi_argus_camera_bin()
          Creates: 4x nvarguscamerasrc
   
     6.2. Create inference bin
          inf_bin = create_bucher_inference_bin(app_context)
          Location: pipeline/bins.py:create_bucher_inference_bin()
          
            6.2.1. Create nozzlenet bin
                   nozzle_bin = create_nozzlenet_inference_bin(app_context)
                   Location: models/nozzlenet/src/bins.py
                   Attaches probe: nozzlenet_src_pad_buffer_probe
            
            6.2.2. Create CSI bin
                   csi_bin = create_csiprobebin(app_context)
                   Location: models/csi/src/bins.py
                   Attaches probe: compute_csi_buffer_probe
   
     6.3. Create output bins
          hr_bin = create_hr_output_bin(app_context)
          udp_bin = create_udpsinkbin(app_context)
          Location: pipeline/bins.py
   
     6.4. Link all elements
          Link camera → inference → outputs
          Location: pipeline/linking.py
   
7. Setup bus watch
   bus = pipeline.get_bus()
   bus.add_watch(GLib.PRIORITY_DEFAULT, bus_call, loop, pipeline)
   Location: main.py:bus_call()
   
8. Start monitoring threads
   start_monitoring_threads(app_context, pipeline)
   Location: monitoring/threads.py:start_monitoring_threads()
   
     8.1. Start FPS thread
          fps_thread = threading.Thread(target=fps_overlay_thread)
          fps_thread.start()
          Location: monitoring/threads.py:fps_overlay_thread()
   
     8.2. Start override monitoring
          override_thread = threading.Thread(target=override_monitoring)
          override_thread.start()
          Location: monitoring/threads.py:override_monitoring()
   
9. Set pipeline to PLAYING
   pipeline.set_state(Gst.State.PLAYING)
   Location: main.py:220
   
10. Enter main loop
    loop = GLib.MainLoop()
    loop.run()
    Location: main.py:230
    
    ↓
    
    [Pipeline now processing buffers]
```

---

## 🔍 Key Component Locations

### Main Entry Points

| Component | File | Key Functions |
|-----------|------|---------------|
| **Application Entry** | `pipeline/src/main.py` | `main()`, `initialize_cameras_wrapper()`, `bus_call()` |
| **Context Setup** | `pipeline/src/context.py` | `setup_app_context()`, `Config.__init__()`, `AppContext.__init__()` |
| **Path Management** | `pipeline/src/utils/paths.py` | `get_smartassist_root()`, `get_config_path()`, `get_dbc_path()` |

### Pipeline Building

| Component | File | Key Functions |
|-----------|------|---------------|
| **Pipeline Builder** | `pipeline/src/pipeline/builder.py` | `build_pipeline()`, `create_multi_argus_camera_bin()` |
| **Bins Creation** | `pipeline/src/pipeline/bins.py` | `create_bucher_inference_bin()`, `create_udpsinkbin()`, `create_hr_output_bin()` |
| **Element Creation** | `pipeline/src/pipeline/elements.py` | `make_element()`, `get_static_pad()` |
| **Linking** | `pipeline/src/pipeline/linking.py` | `link_static_srcpad_pad_to_request_sinkpad()`, etc. |

### Model Processing

| Component | File | Key Functions |
|-----------|------|---------------|
| **CSI Bins** | `models/csi/src/bins.py` | `create_csiprobebin()` |
| **CSI Probes** | `models/csi/src/probes.py` | `compute_csi_buffer_probe()` |
| **CSI Computation** | `models/csi/src/computation.py` | `compute_csi()`, `create_filtering_masks()`, `compute_road_area()`, `compute_garbage_area()`, `get_discrete_csi()` |
| **Nozzlenet Bins** | `models/nozzlenet/src/bins.py` | `create_nozzlenet_inference_bin()` |
| **Nozzlenet Probes** | `models/nozzlenet/src/probes.py` | `nozzlenet_src_pad_buffer_probe()` |
| **State Machine** | `models/nozzlenet/src/state_machine.py` | `SmartStateMachine.status_send()`, `fan_speed` property, `nozzle_state` property |
| **Constants** | `models/nozzlenet/src/constants.py` | Class IDs, state mappings, colors |

### Communication

| Component | File | Key Functions |
|-----------|------|---------------|
| **CAN Client** | `pipeline/src/can/client.py` | `CANClient.connect()`, `send_data()`, `update_can_bytes()`, `get_override_state()` |
| **CAN Server** | `services/can-server/src/main.py` | `CanServer.monitor_can_bus1()`, `start_socket_server()`, `can_send_on_1F7()` |

### Monitoring

| Component | File | Key Functions |
|-----------|------|---------------|
| **Monitoring Threads** | `pipeline/src/monitoring/threads.py` | `fps_overlay_thread()`, `override_monitoring()` |
| **Systemd Integration** | `pipeline/src/utils/systemd.py` | `notify_systemd()`, `load_latest_init_status()`, `unix_socket_server()` |

---

## 📈 Performance Metrics

### Execution Timing

**Startup sequence:**
```
[0.0s]  Python interpreter start
[0.2s]  Imports complete
[0.3s]  Gst.init() complete
[0.5s]  Context setup complete
[0.7s]  Configuration loaded
[1.0s]  Pipeline built
[2.0s]  Pipeline PLAYING
[2.5s]  First frame processed
```

**Per-frame processing:**
```
[0ms]   Buffer arrives from camera
[5ms]   Nozzle inference complete
[10ms]  CSI computation complete
[15ms]  OSD rendering complete
[20ms]  H.265 encoding complete
[25ms]  UDP transmission complete
```

---

## 🎯 Critical Paths

### Path 1: Nozzle Detection → CAN Output
```
Camera → nvinfer → nozzlenet_probe → StateMachine → CANClient → Socket → CAN Server → CAN Bus

Latency: ~50-100ms
Location chain:
- models/nozzlenet/src/probes.py:30
  → models/nozzlenet/src/state_machine.py:80
    → pipeline/src/can/client.py:150
      → pipeline/src/can/client.py:100 (socket send)
        → services/can-server/src/main.py (receive)
          → CAN bus 0x1F7 message
```

### Path 2: CSI Computation → CSV Log
```
Camera → nvinfer (road+garbage) → csi_probe → compute_csi → CSV write

Latency: ~30-50ms
Location chain:
- models/csi/src/probes.py:30
  → models/csi/src/computation.py:80
    → models/csi/src/computation.py:150 (road area)
      → models/csi/src/computation.py:180 (garbage area)
        → models/csi/src/computation.py:200 (discrete CSI)
          → models/csi/src/probes.py:180 (CSV write)
```

### Path 3: Camera → Video Output
```
Camera → converter → tiler → osd → H.265 encoder → UDP sink

Latency: ~40-80ms
Location chain:
- pipeline/src/pipeline/builder.py:create_multi_argus_camera_bin()
  → pipeline/src/pipeline/bins.py:create_bucher_inference_bin()
    → pipeline/src/pipeline/bins.py:create_udpsinkbin()
      → Network transmission
```

---

**Document Version:** 1.0  
**Last Updated:** December 13, 2025  
**Covers:** SmartAssist 2.0 modular architecture
