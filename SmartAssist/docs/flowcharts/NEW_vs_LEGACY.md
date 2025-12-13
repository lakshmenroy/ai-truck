# 📚 Legacy vs New Structure Comparison

## Side-by-Side Architecture

### Legacy (Monolithic)
```
pipeline_w_logging.py (2000 lines)
├─ main()
├─ create_multi_argus_camera_bin()
├─ create_bucher_inference_bin()
├─ INLINE: nozzlenet inference (300 lines)
├─ INLINE: CSI computation (200 lines)
├─ create_hr_output_bin()
├─ create_udpsinkbin()
├─ fps_overlay_thread()
├─ override_monitoring()
└─ bus_call()
```

### New (Modular)
```
pipeline/src/
├─ main.py (~150 lines)
├─ context.py
├─ pipeline/
│  ├─ builder.py
│  ├─ bins.py
│  ├─ elements.py
│  └─ linking.py
├─ monitoring/
│  └─ threads.py
├─ can/
│  └─ client.py
└─ utils/
   ├─ config.py
   ├─ paths.py
   └─ systemd.py

models/csi/src/
├─ bins.py
├─ probes.py
└─ computation.py

models/nozzlenet/src/
├─ bins.py
├─ probes.py
├─ state_machine.py
└─ constants.py
```

## What Changed vs What Stayed Same

### Structure Changes ✅
- Monolithic → Modular
- Inline code → Extracted modules
- Hardcoded paths → Central path management
- bucher-* → smartassist-* naming

### Functionality Unchanged ❌
- GStreamer topology: IDENTICAL
- AI models: IDENTICAL
- CAN protocol: IDENTICAL
- State machine: IDENTICAL
- CSI calculation: IDENTICAL

## Detailed Comparison

| Aspect | Legacy | New | Status |
|--------|--------|-----|--------|
| **Structure** | 1 file (2000 lines) | 20+ files (~100 lines each) | ✅ Changed |
| **GStreamer** | 4 cameras → tee → inference | 4 cameras → tee → inference | ❌ Same |
| **Nozzle Detection** | Inline in pipeline | models/nozzlenet/ | ✅ Extracted |
| **CSI Computation** | Inline in pipeline | models/csi/ | ✅ Extracted |
| **State Machine** | Same logic | Same logic | ❌ Same |
| **CAN Messages** | 0x1F7, 0x0F7 | 0x1F7, 0x0F7 | ❌ Same |
| **Paths** | Hardcoded | paths.py | ✅ Improved |
| **Services** | bucher-* | smartassist-* | ✅ Renamed |
