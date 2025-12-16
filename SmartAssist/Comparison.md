# SmartAssist Architecture Decision: From Legacy to Future-Proof Structure

---

## Table of Contents

- [Executive Summary](#executive-summary)
- [Current State: Legacy Pipeline](#current-state-legacy-pipeline)
- [Future Requirements](#future-requirements)
- [Four Architecture Options](#four-architecture-options)
  - [Option 0: Legacy (Current State)](#option-0-legacy-current-state)
  - [Option 1: Monorepo with Independent Versioning](#option-1-monorepo-with-independent-versioning)
  - [Option 2: Package Registry (Recommended)](#option-2-package-registry-recommended)
  - [Option 3: Submodules](#option-3-submodules)
- [Deployment Considerations](#deployment-considerations)
- [Comprehensive Comparison](#comprehensive-comparison)
- [Migration Path](#migration-path)
- [Final Recommendation](#final-recommendation)

---

## Executive Summary

**Current Situation:**
- Legacy monolithic pipeline (2000+ lines, flat directory structure)
- No CI/CD, manual deployment
- Single configuration: 4 cameras, nozzlenet + CSI

**Future Needs:**
- Multiple truck types: full, CSI-only, compact, heavy-duty
- Independent application versions
- Shared core library (smartassist-core)
- Snap packages for Ubuntu Core deployment
- CI/CD automation

**Recommendation:** **Option 2 (Package Registry)** - Separate repositories with internal PyPI for smartassist-core

**Why:** True independence, clear versioning, standard Python practice, clean snap packages, future-proof for Canonical Core deployment

---

## Current State: Legacy Pipeline

### Legacy Structure (Before SSWP-29)

```yaml
Pipeline/                            # Legacy monolithic structure
├── main.py                          # 2000+ lines, everything in one file
│   ├── GStreamer pipeline setup
│   ├── Camera initialization
│   ├── Nozzlenet inference
│   ├── CSI inference
│   ├── CAN communication
│   ├── Monitoring threads
│   └── State machine
│
├── config.yaml                      # Single configuration file
│   cameras: 4
│   models: [nozzlenet, csi]
│
├── models/
│   ├── nozzlenet/
│   │   └── weights/
│   └── csi/
│       └── weights/
│
└── README.md

# No version control structure
# No CI/CD
# No independent components
# No package management
# Flat directory - everything mixed together
```

### Legacy Deployment Process

```bash
# Manual deployment (current method)
# On development machine:
tar -czf pipeline.tar.gz Pipeline/
scp pipeline.tar.gz truck@192.168.1.100:/home/truck/

# On truck (Jetson Orin):
ssh truck@172.16.1.x?
cd /home/truck
tar -xzf pipeline.tar.gz
cd Pipeline

# Manual service setup
sudo cp smartassist.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable smartassist
sudo systemctl start smartassist

# Check status
systemctl status smartassist
```

### Legacy Problems

1. **Monolithic Code:**
   - 2000+ lines in single file
   - Hard to maintain
   - Hard to test components independently
   - No code reusability

2. **No Version Control:**
   - No semantic versioning
   - No release tags
   - Manual tracking: "which version is on truck VIN-12345?"

3. **No CI/CD:**
   - Manual builds
   - Manual testing
   - No automated packaging
   - Human error prone

4. **No Modularity:**
   - Can't reuse GStreamer components
   - Can't create different configurations
   - Duplicate code for new truck types

5. **Deployment Issues:**
   - Manual scp to every truck
   - Manual service setup
   - No rollback mechanism
   - No SBOM tracking (The tool we use is called Sbom but doesn't give the actual functionality of what SBOM is. Need to rename it to Manifest? - output feels mixture of manifest and sbom)

6. **No Flexibility:**
   - Can't support smartcsi-only (without code duplication)
   - Can't support compact truck (without code duplication)
   - Adding new type = copy entire codebase

### Legacy vs Future Needs

| Aspect | Legacy | Needed |
|--------|--------|--------|
| **Code Structure** | Monolithic | Modular |
| **Versions** | None | Semantic versioning |
| **Applications** | One configuration | Multiple truck types |
| **Deployment** | Manual scp | Automated snap packages |
| **CI/CD** | None | Automated builds/tests |
| **Code Reuse** | Copy/paste | Shared library |
| **SBOM** | None | Required for compliance |
| **Rollback** | Manual | Snap revert |

---

## Future Requirements

### Multiple Truck Configurations

1. **smartassist-full** (v2.1.x)
   - 4 cameras
   - Nozzlenet + CSI models
   - Full-size sweeper trucks
   - Complete AI assistance

2. **smartcsi-only** (v1.3.x)
   - 4 cameras
   - CSI model only (no nozzlenet)
   - Trucks without nozzle detection need
   - Simpler, faster

3. **compact-truck** (v1.0.x)
   - 2 cameras? 4 cameras?
   - Different nozzlenet variant
   - CSI model
   - Compact sweeper trucks

4. **Future: heavy-duty, multi-purpose, etc.**

### Core Principle

```yaml
smartassist-core = Shared library (like numpy)
- GStreamer components
- CAN communication
- Monitoring utilities
- Version: Independent (v1.5.0, v1.6.0)

Applications = Independent products
- Use smartassist-core as dependency
- Version independently
- Bug in one doesn't affect others
```

### Key Requirement

```yaml
Bug in smartassist-full v2.1.5:
  Fix → smartassist-full v2.1.6
  smartcsi-only stays at v1.3.2 ✅

Enhancement in smartassist-core v1.5.0 → v1.6.0:
  smartassist-full v2.1.6 → upgrades to core v1.6.0
  smartcsi-only v1.3.2 → stays on core v1.5.0 (upgrades later)
```

---

## Four Architecture Options

### Option 0: Legacy (Current State)

**Status:** Baseline - what we have now

**Structure:**
```yaml
Pipeline/
└── main.py (2000+ lines, monolithic)
```

**Pros:**
- Simple structure (one file)
- Everyone knows where code is

**Cons:**
- Everything listed in "Legacy Problems" above
- Cannot support multiple truck types
- No code reusability
- No CI/CD
- No version control
- Manual deployment
- Not scalable
- Not maintainable

**Verdict:** Must migrate away from this

---

### Option 1: Monorepo with Independent Versioning

**Philosophy:** Single repository, but independently versioned applications

**Structure:**

```yaml
SmartAssist/                         # Single monorepo
├── .github/workflows/
│   ├── build-full-snap.yml          # CI for full snap
│   ├── build-csi-snap.yml           # CI for csi snap
│   └── build-compact-snap.yml       # CI for compact snap
│
├── smartassist_core/                # Shared library
│   ├── setup.py                     # Version: 1.5.0
│   ├── gstreamer/
│   │   ├── bins/
│   │   ├── elements/
│   │   └── probes/
│   ├── can/
│   │   ├── client.py
│   │   └── protocol.py
│   └── monitoring/
│       └── threads.py
│
├── models/                          # Shared models
│   ├── csi/
│   │   ├── src/
│   │   └── weights/
│   └── nozzlenet/
│       ├── src/
│       └── weights/
│
├── applications/
│   ├── smartassist_full/            # Independent product
│   │   ├── manifest.yaml            # Version: 2.1.5
│   │   ├── requirements.txt         # smartassist-core>=1.5.0
│   │   ├── snap/snapcraft.yaml
│   │   ├── main.py
│   │   └── config/
│   │
│   ├── smartcsi_only/               # Independent product
│   │   ├── manifest.yaml            # Version: 1.3.2
│   │   ├── requirements.txt         # smartassist-core>=1.4.0
│   │   ├── snap/snapcraft.yaml
│   │   ├── main.py
│   │   └── config/
│   │
│   └── compact_truck/               # Independent product
│       ├── manifest.yaml            # Version: 1.0.3
│       ├── requirements.txt         # smartassist-core>=1.5.0
│       ├── snap/snapcraft.yaml
│       ├── main.py
│       └── config/
│
└── services/                        # Shared services
    ├── can-server/
    ├── gpio-monitor/
    └── health-monitor/
```

**CI/CD for Snap Building:**

```yaml
# .github/workflows/build-csi-snap.yml
name: Build SmartCSI Snap

on:
  push:
    tags:
      - 'smartcsi-only-v*'

jobs:
  build-snap:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Build snap
        uses: snapcore/action-build@v1
        with:
          path: applications/smartcsi_only  # 👈 Must specify path
      
      - name: Upload artifact
        uses: actions/upload-artifact@v3
        with:
          name: smartcsi-snap
          path: applications/smartcsi_only/*.snap
```

**Snap Package (What Edge Device Gets):**

```bash
# Build smartcsi-only snap from monorepo
cd SmartAssist
snapcraft --project applications/smartcsi_only

# Output: smartcsi-only_1.3.2_arm64.snap
# Contains ONLY:
# - applications/smartcsi_only/main.py
# - applications/smartcsi_only/config/
# - smartassist-core (bundled via pip)
# - models/csi/ (bundled)

# Does NOT contain smartassist_full or compact_truck code
```

**Pros:**
- All code in one repository
- Can test applications together
- Shared models and services in one place
- Single git clone for developers
- Each snap contains only its application

**Cons:**
- Multiple CI workflows in one repo (complex)
- Tag management: `smartcsi-only-v1.3.2`, `smartassist-full-v2.1.5`
- All applications see all changes (even if unaffected)
- snap/snapcraft.yaml must be in subdirectories
- CI must specify paths for each application
- Not truly independent

**Deployment:**

```bash
# Manual (current): ?
cd SmartAssist/applications/smartcsi_only
snapcraft
scp smartcsi-only_*.snap truck@192.168.1.100:

# Future (automated):
git tag smartcsi-only-v1.3.3
git push --tags
# CI builds and publishes snap automatically
```

---

### Option 2: Package Registry (Recommended)

**Philosophy:** Separate repositories, shared core via internal PyPI

**Structure:**

```yaml
Repository 1: smartassist-core       # Shared library
├── setup.py                         # Version: 1.5.0
├── smartassist_core/
│   ├── __init__.py
│   ├── gstreamer/
│   │   ├── bins/
│   │   │   ├── camera_bin.py
│   │   │   ├── inference_bin.py
│   │   │   └── tee_bin.py
│   │   ├── elements/
│   │   │   ├── factory.py
│   │   │   └── linking.py
│   │   └── probes/
│   │       ├── base_probe.py
│   │       └── fps_probe.py
│   ├── can/
│   │   ├── client.py
│   │   └── protocol.py
│   └── monitoring/
│       └── threads.py
├── tests/
│   ├── test_camera_bin.py
│   └── test_can_client.py
└── .github/workflows/
    └── publish-pypi.yml             # Publishes to internal PyPI/ Internal registry

Repository 2: smartassist-models     # Shared models
├── setup.py                         # Version: 2.0.0
├── smartassist_models/
│   ├── csi/
│   │   ├── src/
│   │   ├── weights/
│   │   └── config/
│   └── nozzlenet/
│       ├── src/
│       ├── weights/
│       └── config/
└── .github/workflows/
    └── publish-pypi.yml             # Publishes to internal PyPI/ Internal registry

Repository 3: smartassist-full       # Application 1 (Independent)
├── manifest.yaml                    # Version: 2.1.5
├── requirements.txt
│   smartassist-core>=1.5.0,<2.0.0
│   smartassist-models>=2.0.0,<3.0.0
├── snap/
│   └── snapcraft.yaml               # Snap config at root
├── main.py
├── config/
│   └── pipeline_config.yaml
├── README.md
└── .github/workflows/
    └── build-snap.yml               # Simple - builds from root

Repository 4: smartcsi-only          # Application 2 (Independent)
├── manifest.yaml                    # Version: 1.3.2
├── requirements.txt
│   smartassist-core>=1.4.0,<2.0.0
│   smartassist-models>=2.0.0,<3.0.0
├── snap/
│   └── snapcraft.yaml
├── main.py
├── config/
│   └── pipeline_config.yaml
├── README.md
└── .github/workflows/
    └── build-snap.yml

Repository 5: compact-truck          # Application 3 (Independent)
├── manifest.yaml                    # Version: 1.0.3
├── requirements.txt
│   smartassist-core>=1.5.0,<2.0.0
│   smartassist-models>=2.0.0,<3.0.0
├── snap/
│   └── snapcraft.yaml
├── main.py
├── config/
│   └── pipeline_config.yaml
├── README.md
└── .github/workflows/
    └── build-snap.yml
```

**smartassist-core/setup.py:**

```python
from setuptools import setup, find_packages

setup(
    name='smartassist-core',
    version='1.5.0',
    packages=find_packages(),
    install_requires=[
        'numpy>=1.24.0',
        'opencv-python>=4.5.0',
        'pygobject>=3.42.0',
    ],
    python_requires='>=3.8',
)
```

**smartcsi-only/snap/snapcraft.yaml:**

```yaml
name: smartcsi-only
version: '1.3.2'
summary: SmartCSI road cleanliness detection
description: |
  CSI-only system for 4-camera trucks. Detects road cleanliness
  without nozzle detection.

base: core22
confinement: strict
grade: stable

architectures:
  - build-on: arm64
    build-for: arm64

apps:
  smartcsi-only:
    command: bin/python3 main.py
    daemon: simple
    restart-condition: always
    plugs:
      - network
      - network-bind
      - camera
      - hardware-observe
      - gpio
      - serial-port

parts:
  smartcsi-app:
    plugin: python
    source: .                        # Root of repo
    requirements:
      - requirements.txt             # Pulls smartassist-core from PyPI
    stage-packages:
      - libgstreamer1.0-0
      - gstreamer1.0-plugins-base
      - gstreamer1.0-plugins-good
      - python3-gi
```

**smartcsi-only/.github/workflows/build-snap.yml:**

```yaml
name: Build and Test Snap

on:
  push:
    tags:
      - 'v*.*.*'                     # Simple tag: v1.3.2

jobs:
  build-snap:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v3
      
      - name: Build snap
        uses: snapcore/action-build@v1
        id: build
        # No path specification - builds from root
      
      - name: Upload artifact
        uses: actions/upload-artifact@v3
        with:
          name: smartcsi-snap
          path: ${{ steps.build.outputs.snap }}
      
      - name: Publish to Snap Store (optional)
        if: startsWith(github.ref, 'refs/tags/')
        uses: snapcore/action-publish@v1
        env:
          SNAPCRAFT_STORE_CREDENTIALS: ${{ secrets.STORE_LOGIN }}
        with:
          snap: ${{ steps.build.outputs.snap }}
          release: stable
```

**Snap Package (What Edge Device Gets):**

```yaml
# CI builds: smartcsi-only_1.3.2_arm64.snap
# Contains:
# - main.py
# - config/
# - smartassist-core v1.4.0 (from PyPI)
# - smartassist-models v2.0.0 (from PyPI)

# Clean, minimal package
# No smartassist-full code
# No compact-truck code
```

**How It Works:**

```python
# smartassist-full/main.py
from smartassist_core.gstreamer.bins import CameraBin, InferenceBin
from smartassist_core.can import CANClient
from smartassist_models.nozzlenet import NozzlenetBin
from smartassist_models.csi import CSIBin

# Build pipeline for full system
camera_bin = CameraBin(num_cameras=4)
nozzlenet_bin = NozzlenetBin()
csi_bin = CSIBin()

camera_bin.link(nozzlenet_bin)
camera_bin.link(csi_bin)
```

```python
# smartcsi-only/main.py
from smartassist_core.gstreamer.bins import CameraBin, InferenceBin
from smartassist_core.can import CANClient
from smartassist_models.csi import CSIBin

# Build pipeline for CSI-only (no nozzlenet)
camera_bin = CameraBin(num_cameras=4)
csi_bin = CSIBin()

camera_bin.link(csi_bin)
```

**Pros:**
- True independence: Each application is separate repo
- Independent versioning: Bug in one doesn't affect others
- Clean snap packages: Each repo builds cleanly from root
- Simple CI/CD: One workflow per repo
- Clean tags: `v1.3.2` not `smartcsi-only-v1.3.2`
- Standard Python: pip install smartassist-core==1.5.0
- Core is stable library: Applications choose when to upgrade
- New truck types: Create new repo (zero impact on existing)
- Customer deployment: Clone only needed repo
- Clean SBOM: Per application

**Cons:**
- Need internal PyPI server (one-time setup)
- More repos to manage (but that's the goal)
- Core changes require updating applications (when they choose)

**Deployment:**

```bash
# Manual (current):
cd smartcsi-only
snapcraft
scp smartcsi-only_*.snap truck@172.16.1.x?

# Future (automated):
git tag v1.3.3
git push --tags
# CI builds and publishes snap automatically
# Edge devices: snap refresh smartcsi-only
```

---

### Option 3: Submodules

**Philosophy:** Separate repositories with Git submodules

**Structure:**

```yaml
Repository 1: smartassist-core       # Submodule
├── gstreamer/
├── can/
└── monitoring/

Repository 2: smartassist-models     # Submodule
├── csi/
└── nozzlenet/

Repository 3: smartassist-full       # Application 1
├── .gitmodules
│   [submodule "core"]
│     path = smartassist-core
│     url = github.com/company/smartassist-core.git
│   [submodule "models"]
│     path = smartassist-models
│     url = github.com/company/smartassist-models.git
├── smartassist-core/                # Submodule → commit abc123
├── smartassist-models/              # Submodule → commit def456
├── snap/
│   └── snapcraft.yaml
├── main.py
└── config/

Repository 4: smartcsi-only          # Application 2
├── .gitmodules
├── smartassist-core/                # Submodule → commit abc123
├── smartassist-models/              # Submodule → commit def456
├── snap/
│   └── snapcraft.yaml
├── main.py
└── config/

Repository 5: compact-truck          # Application 3
├── .gitmodules
├── smartassist-core/                # Submodule → commit ghi789
├── smartassist-models/              # Submodule → commit jkl012
├── snap/
│   └── snapcraft.yaml
├── main.py
└── config/
```

**snap/snapcraft.yaml with submodules:**

```yaml
name: smartcsi-only
version: '1.3.2'
# ... same as Option 2 ...

parts:
  smartcsi-app:
    plugin: python
    source: .
    build-packages:
      - git                          # Need git for submodules
    override-pull: |
      snapcraftctl pull
      git submodule update --init --recursive
    # Rest same as Option 2
```

**manifest.yaml (Problem):**

```yaml
# smartassist-full/manifest.yaml
application: smartassist_full
version: "2.1.5"

dependencies:
  core_commit: "abc123"              #  What version is this?
  models_commit: "def456"            #  What version is this?
  
# Compare to Option 2:
dependencies:
  smartassist_core: "1.5.0"         #  Clear semantic version
  smartassist_models: "2.0.0"       #  Clear semantic version
```

**Pros:**
- True repository independence
- No package registry needed
- Each application is separate repo

**Cons:**
- No semantic versions (Git commit SHAs only)
- manifest.yaml unclear: "commit abc123" (what version?)
- SBOM compliance difficult (auditors want v1.5.0, not abc123)
- Git submodule complexity (detached HEAD, manual updates)
- snapcraft.yaml more complex (must handle submodules)
- Not standard Python practice
- Version tracking requires Git archaeology

**Deployment:**

```bash
# Manual (current):
cd smartcsi-only
git submodule update --init --recursive
snapcraft
scp smartcsi-only_*.snap truck@172.16.1.x?:

# CI must handle submodules carefully
```

---

## Deployment Considerations

### Current State: Manual Deployment

**Process Today:**

```bash
# Developer builds package
cd smartcsi-only
snapcraft  # Or: tar -czf smartcsi-only.tar.gz

# Transfer to truck
scp smartcsi-only_*.snap truck@172.16.1.x?:

# Install on truck
ssh truck@192.168.1.100
sudo snap install smartcsi-only_*.snap --dangerous

# Or manual systemd setup (non-snap)
sudo cp smartcsi.service /etc/systemd/system/
sudo systemctl enable smartcsi
sudo systemctl start smartcsi
```

**Works with all options:**
- Option 1: Build from monorepo subdirectory
- Option 2: Build from separate repo (cleanest)
- Option 3: Build with submodules (most complex)

### Future State: Canonical Ubuntu Core

**Process in Future:**

```bash
# Developer
git tag v1.3.3
git push --tags

# CI/CD (GitHub Actions)
# Builds snap automatically
# Publishes to Snap Store (or private store)

# Edge Device (Jetson with Ubuntu Core)
snap refresh smartcsi-only
# Automatically downloads v1.3.3
# Automatically restarts service
# Automatic rollback if failure
```

**How Options Compare:**

| Aspect | Option 1: Monorepo | Option 2: Package Registry | Option 3: Submodules |
|--------|-------------------|---------------------------|---------------------|
| **Manual snap build** | `snapcraft --project apps/csi` | `snapcraft` (root) | `snapcraft` (root) |
| **CI snap build** | Specify path in workflow | Build from root | Handle submodules |
| **Snap size** | Same (~500MB) | Same (~500MB) | Same (~500MB) |
| **Snap contents** | Only app code | Only app code | Only app code |
| **Auto-update** | Works | Works | Works |
| **Rollback** | `snap revert` | `snap revert` | `snap revert` |

**All options work with snaps, but Option 2 is cleanest.**

---

## Comprehensive Comparison

### Complete Comparison Table

| Aspect | Legacy | Option 1: Monorepo | Option 2: Package Registry | Option 3: Submodules |
|--------|--------|-------------------|---------------------------|---------------------|
| **Code Structure** | Monolithic | Modular | Modular | Modular |
| **Version Control** | None | Git tags per app | Git repos per app | Git repos per app |
| **Semantic Versions** | ❌ None | ✅ Yes | ✅ Yes | ❌ No (commits) |
| **CI/CD** | ❌ None | Complex (multiple) | ✅ Simple (one per repo) | Medium (submodules) |
| **App Independence** | ❌ N/A | Partial (same repo) | ✅ True (separate repos) | ✅ True (separate repos) |
| **Bug Fix Isolation** | ❌ No | ✅ Yes | ✅ Yes | ✅ Yes |
| **Code Reusability** | ❌ Copy/paste | ✅ Shared library | ✅ pip install | ✅ Submodules |
| **Version Clarity** | ❌ None | ✅ manifest.yaml | ✅ requirements.txt | ❌ Git SHAs |
| **SBOM Generation** | ❌ None | ✅ Per app | ✅ Per app (standard) | ⚠️ Complex (commits) |
| **Snap Building** | ❌ N/A | Medium (specify path) | ✅ Simple (root) | Medium (submodules) |
| **Snap Size** | N/A | ~500MB | ~500MB | ~500MB |
| **Customer Deploy** | Manual scp | Clone monorepo | ✅ Clone specific repo | Clone specific repo |
| **New Truck Type** | ❌ Duplicate code | Add to monorepo | ✅ New repo | New repo |
| **Core Upgrades** | ❌ Manual everywhere | All see changes | ✅ Apps choose when | Apps choose (unclear version) |
| **Python Standard** | ❌ No | Partial | ✅ Yes (pip) | ❌ No |
| **ISO 26262 Compliance** | ❌ No | ✅ Yes | ✅ Yes (best) | ⚠️ Difficult |
| **Maintainability** | ❌ Poor | Good | ✅ Excellent | Medium |
| **Scalability** | ❌ Poor | Medium | ✅ Excellent | Medium |

### What is the ISO 26262 standard?
ISO 26262-6:2018 is the most recent version of the standard for the development of software for safety-related systems installed in most road vehicles.

#### How does VectorCAST support ISO 26262?
- This whitepaper is intended to serve as a reference to show how the VectorCAST products can be used to satisfy the verification and validation requirements specified in the ISO 26262 standard. In summary this whitepaper overviews:

- Verification and validation standards for automotive software
#### How VectorCAST supports compliance with industry regulations
- Methods for software unit testing using VectorCAST


### Scoring Summary (laksh's Score - not actual score)

| Criteria | Legacy | Option 1 | Option 2 | Option 3 |
|----------|--------|----------|----------|----------|
| **Code Quality** | 3/10 | 7/10 | 9/10 | 7/10 |
| **Maintainability** | 2/10 | 7/10 | 9/10 | 6/10 |
| **Scalability** | 1/10 | 6/10 | 10/10 | 7/10 |
| **Developer Experience** | 3/10 | 7/10 | 9/10 | 5/10 |
| **Deployment** | 2/10 | 7/10 | 9/10 | 6/10 |
| **Compliance** | 0/10 | 8/10 | 10/10 | 5/10 |
| **Future-Proof** | 0/10 | 6/10 | 10/10 | 6/10 |
| **TOTAL** | **11/70** | **48/70** | **66/70** | **42/70** |


---

## Migration Path

### Phase 1: Setup Infrastructure

**Goal:** Setup internal PyPI server for smartassist-core


### Phase 2: Extract Core Library

**Goal:** Create smartassist-core repository and publish v1.0.0

```bash
# Create smartassist-core repo
mkdir smartassist-core
cd smartassist-core
git init

# Copy core components from legacy Pipeline/
cp -r ../Pipeline/gstreamer_components/ smartassist_core/gstreamer/
cp -r ../Pipeline/can_client.py smartassist_core/can/client.py
cp -r ../Pipeline/monitoring.py smartassist_core/monitoring/threads.py

# Create setup.py
cat > setup.py << 'EOF'
from setuptools import setup, find_packages

setup(
    name='smartassist-core',
    version='1.0.0',
    packages=find_packages(),
    install_requires=[
        'numpy>=1.24.0',
        'opencv-python>=4.5.0',
        'pygobject>=3.42.0',
    ],
    python_requires='>=3.8',
)
EOF

# Build and publish
python -m build
twine upload --repository-url http://pypi.internal:8080 dist/*

# Test
pip install smartassist-core==1.0.0
python -c "from smartassist_core.gstreamer.bins import CameraBin; print('Success!')"
```

### Phase 3: Create First Application

**Goal:** Create smartcsi-only repository using smartassist-core

```bash
# Create smartcsi-only repo
mkdir smartcsi-only
cd smartcsi-only
git init

# Create requirements.txt
cat > requirements.txt << EOF
smartassist-core>=1.0.0,<2.0.0
numpy>=1.24.0
EOF

# Create main.py
cat > main.py << 'EOF'
from smartassist_core.gstreamer.bins import CameraBin, InferenceBin
from smartassist_core.can import CANClient

def main():
    camera_bin = CameraBin(num_cameras=4)
    csi_bin = InferenceBin(model='csi')
    can_client = CANClient()
    
    camera_bin.link(csi_bin)
    camera_bin.run()

if __name__ == '__main__':
    main()
EOF

# Create snap/snapcraft.yaml
mkdir snap
cat > snap/snapcraft.yaml << 'EOF'
name: smartcsi-only
version: '1.0.0'
summary: SmartCSI road cleanliness detection
# ... (complete snapcraft.yaml from Option 2)
EOF

# Test locally
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py

# Build snap
snapcraft

# Test snap
sudo snap install smartcsi-only_*.snap --dangerous
```

### Phase 4: Create Remaining Applications 

**Goal:** Create smartassist-full and compact-truck repos

```bash
# Create smartassist-full repo
# Similar to smartcsi-only, but with nozzlenet

# Create compact-truck repo
# Similar to smartcsi-only, but different models?
```

### Phase 5: Setup CI/CD 

**Goal:** Automate snap building and publishing

```bash
# For each application repo, add .github/workflows/build-snap.yml
# From Option 2 example above

# Test CI/CD
git tag v1.0.1
git push --tags
# Watch GitHub Actions build and publish snap
```

### Phase 6: Deploy to Test Trucks 

**Goal:** Test new architecture on real hardware

```bash
# Test truck 1: smartcsi-only
scp smartcsi-only_*.snap truck1@172.16.1.x?:
ssh truck1@172.16.1.x?
sudo snap install smartcsi-only_*.snap --dangerous

# Test truck 2: smartassist-full
scp smartassist-full_*.snap truck2@172.16.1.x?:
ssh truck2@172.16.1.x?
sudo snap install smartassist-full_*.snap --dangerous
```

---

## Recommendation

### Choose Option 2: Package Registry with Separate Repos

**Why This is the Best Choice:**

### 1. True Independence 

```yaml
Bug in smartassist-full v2.1.5:
  Fix → smartassist-full v2.1.6 
  smartcsi-only v1.3.2 unaffected 
  compact-truck v1.0.3 unaffected 

No accidental version bumps
No coordination overhead
```

### 2. Clear Version Tracking 

```yaml
requirements.txt:
  smartassist-core==1.5.0 # Semantic version, not Git commit
  
manifest.yaml:
  application: smartcsi_only
  version: "1.3.2"
  dependencies:
    smartassist_core: "1.5.0" # Clear for auditors
    
ISO 26262 compliant
EU CRA compliant
```

### 3. Standard Python Practice 

```bash
pip install smartassist-core==1.5.0  # Standard workflow
Familiar to all Python developers
No Git submodule expertise needed
```

### 4. Clean Snap Packages 

```bash
# Option 2: Simple
cd smartcsi-only
snapcraft # Builds from root
snap install smartcsi-only_*.snap 

# Option 1: Complex
cd SmartAssist
snapcraft --project applications/smartcsi_only # Must specify path

# Option 3: Complex
git submodule update --init --recursive 
snapcraft ⚠️
```

### 5. Simple CI/CD 

```yaml
# Option 2: One workflow per repo
smartcsi-only/.github/workflows/build-snap.yml 

# Option 1: Multiple workflows in monorepo
SmartAssist/.github/workflows/build-full-snap.yml
SmartAssist/.github/workflows/build-csi-snap.yml 
SmartAssist/.github/workflows/build-compact-snap.yml
# Complex tag management
```

### 6. Customer Deployment 

```bash
# Option 2: Clean
git clone smartcsi-only # Only what they need
cd smartcsi-only
snapcraft

# Option 1: Bloated
git clone SmartAssist # Gets everything
cd SmartAssist/applications/smartcsi_only
# Customer has smartassist-full code they don't need
```

### 7. Future Proof 

```bash
# New truck type? Just create new repo
mkdir heavy-duty-truck
# Zero impact on existing applications 

# Core enhancement?
# Applications upgrade when they choose 

# Canonical Ubuntu Core?
# Standard snap workflow 
```

### 8. Compliance 

```bash
Auditor: "What version of core is on truck VIN-12345?"

# Option 2:
Answer: "smartassist-core v1.5.0" 
Evidence: requirements.txt + manifest.yaml
Time: 30 seconds

# Option 3:
Answer: "Core commit abc123..." 
Evidence: Must check Git history
Time: 10 minutes
Auditor: "Unacceptable" 
```

## Conclusion

**Legacy (Option 0):**
- Status: Must migrate away
- Verdict: Not suitable for future

**Option 1 (Monorepo):**
- Status: Workable but not optimal
- Verdict: Better than legacy, but not best choice

**Option 2 (Package Registry):**
- Status: Recommended
- Verdict: Best for independence, compliance, and future growth

**Option 3 (Submodules):**
- Status: Not recommended
- Verdict: Complexity without clear benefits

---

**Decision: Proceed with Option ?**

**Rationale:**
- True application independence
- Clear semantic versioning
- Standard Python practices
- Clean snap packages
- Simple CI/CD
- ISO 26262 & EU CRA compliant
- Future-proof for Canonical Core
- Scalable for new truck types

---
