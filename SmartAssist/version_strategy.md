# SmartAssist Version Strategy & Release Process

**Official Reference:** SSWP-29 (signed SOP)  
**Quick Reference:** This document (for developers)

---

## Table of Contents

- [Semantic Versioning](#semantic-versioning)
- [Version Decision Tree](#version-decision-tree)
- [Tag Management](#tag-management)
- [Release Workflow](#release-workflow)
- [Manifest and SBOM](#manifest-and-sbom)
- [Quick Reference](#quick-reference)

---

## Semantic Versioning

SmartAssist uses **Semantic Versioning (SemVer)**: `MAJOR.MINOR.PATCH`

### Version Components

| Component | When to Increment | Examples |
|-----------|-------------------|----------|
| **MAJOR** | Breaking changes requiring truck reflashing | CAN protocol change, removed API endpoints |
| **MINOR** | New features (backward compatible) | Add OTA support, new AI model |
| **PATCH** | Bug fixes and improvements | Model weight updates, performance fixes |

### Rules

- **MAJOR (X.0.0):** Breaks compatibility with existing trucks
- **MINOR (x.X.0):** Adds functionality, maintains compatibility
- **PATCH (x.x.X):** Fixes/improves without adding functionality

---

## 🌳 Version Decision Tree

Use this flowchart to decide version bumps:

```
Does it BREAK existing trucks?
├─ YES → MAJOR bump (1.x.x → 2.0.0)
│         Examples:
│         • Changed CAN message format
│         • Removed required CAN messages
│         • Changed config file structure incompatibly
│
└─ NO ↓

Does it ADD new functionality?
├─ YES → MINOR bump (x.1.x → x.2.0)
│         Examples:
│         • Added OTA update support
│         • Added new AI model
│         • Added log uploader
│         • Added new CAN messages (keeping old ones)
│
└─ NO ↓

Is it just improvements/fixes?
└─ YES → PATCH bump (x.x.1 → x.x.2)
          Examples:
          • Fixed nozzle detection bug
          • Updated model weights (same architecture)
          • Performance optimization
          • Security patches
```

### Examples

| Change | Breaking? | New Feature? | Version | Rationale |
|--------|-----------|--------------|---------|-----------|
| nozzlenet 2.5.3→2.5.4 (bug fix) | ❌ | ❌ | 1.0.0 → 1.0.1 | Bug fix only |
| Add OTA support | ❌ | ✅ | 1.0.0 → 1.1.0 | New feature |
| CAN v1→v2 protocol | ✅ | N/A | 1.1.0 → 2.0.0 | Breaking change |
| nozzlenet fix + OTA feature | ❌ | ✅ | 1.0.0 → 1.1.0 | Feature > fix |
| Pipeline refactor (internal) | ❌ | ❌ | 1.0.0 → 1.0.1 | No external impact |

**Rule:** Most significant change wins!

---

## 🏷️ Tag Management

### Tag Types

| Tag Format | Triggers CI? | Purpose | Examples |
|------------|--------------|---------|----------|
| `v*.*.*` | ✅ YES | Production releases | `v1.0.0`, `v1.1.0` |
| `v*.*.*-rc*` | ⚠️ Optional | Release candidates | `v1.1.0-rc1` |
| `test-*` | ❌ NO | Integration testing | `test-ota-v1` |
| `dev-*` | ❌ NO | Developer testing | `dev-john-fix` |
| `sprint-*` | ❌ NO | Sprint candidates | `sprint-2-rc` |

### CI Configuration

Production releases trigger only on semantic version tags:

```yaml
# .github/workflows/release.yml
on:
  push:
    tags:
      - 'v[0-9]+.[0-9]+.[0-9]+'  # Matches: v1.0.0, v2.1.3
                                 # Ignores: test-*, dev-*, sprint-*
```

### Tag Comparison

CI compares **production tags only**, ignoring all test/dev/sprint tags:

```bash
# CI finds previous production release
PREV_TAG=$(git tag -l 'v[0-9]*.[0-9]*.[0-9]*' | sort -V | tail -2 | head -1)

# CI compares snapshots (not commits!)
git diff $PREV_TAG..$CURRENT_TAG --name-only
```

**Example Timeline:**

```
v1.0.0 (Production)          ← Last release
  ↓
test-nozzlenet-2.5.4         ← CI ignores
  ↓
dev-pipeline-refactor        ← CI ignores
  ↓
sprint-2-candidate           ← CI ignores
  ↓
v1.1.0 (Production)          ← New release

CI compares: v1.0.0 to v1.1.0 (ignores everything in between)
```

---

## 🚀 Release Workflow

### Development Phase (Weeks 1-3)

```bash
# Normal development
git commit -m "feat(ota): add update client"
git commit -m "fix(nozzlenet): improve threshold"

# Create test tags (optional)
git tag test-ota-integration
git push --tags
# → CI does NOT run ✅

# Create sprint tags (optional)
git tag sprint-2-candidate
git push --tags
# → CI does NOT run ✅
```

### Production Release (Week 4)

**Step 1:** Decide version using decision tree

```
Example: Added OTA feature → MINOR bump → v1.1.0
```

**Step 2:** Create production tag

```bash
git tag v1.1.0 -m "Add OTA support and bug fixes"
git push --tags
```

**Step 3:** CI runs automatically

```
1. Environment Setup
   - Checkout code with full history
   - Setup Python, install dependencies

2. Find Previous Production Release
   - Query: v[0-9]*.[0-9]*.[0-9]*
   - Result: v1.0.0

3. Detect Component Changes
   - Run: git diff v1.0.0..v1.1.0 --name-only
   - Detect: models/nozzlenet/, pipeline/

4. Update manifest.yaml
   - version: "1.1.0"
   - build_date: "2025-12-14"
   - commit_hash: "abc123..."
   - nozzlenet_model.version: "2.5.4"

5. Generate SBOM
   - Clone SBOM tool repo
   - Calculate SHA-256 hashes
   - Run pip freeze
   - Output: SBOM.json

6. Validate SBOM
   - Verify CycloneDX format
   - Validate hashes

7. Package Release
   - Create: smartassist-v1.1.0.tar.gz
   - Calculate: checksums.txt

8. Generate Release Notes
   - Extract commit log
   - Format component changes

9. Create GitHub Release
   - Attach: SBOM.json, manifest.yaml, tarball, checksums
   - Publish release notes

Result: ✅ Release v1.1.0 created
```

---

## 📄 Manifest and SBOM

### manifest.yaml (Source of Truth)

**Location:** `SmartAssist/manifest.yaml`

**Characteristics:**
- ✅ Git-tracked
- ✅ Human-readable (YAML)
- ✅ Auto-updated by CI
- ✅ Simple (essential info only)

**Example:**

```yaml
version: "1.1.0"
build_date: "2025-12-14"
commit_hash: "abc123def456"

components:
  pipeline:
    version: "1.1.0"
    path: "pipeline/"
  
  nozzlenet_model:
    version: "2.5.4"
    path: "models/nozzlenet/"
    model_file: "weights/v2.5.4/model.plan"
  
  csi_model:
    version: "2.0.1"
    path: "models/csi/"

hardware:
  platform: "NVIDIA Jetson Orin"
  cameras: 4

software:
  jetpack: "6.0+"
  deepstream: "6.4+"
  python: "3.8+"
```
Compatibility matrix can look like this.
```yaml
pipeline:
  version: "1.6.0"
  requires:
    csi_model: ">=2.0.0,<3.0.0"  # Requires CSI 2.0+!
    nozzlenet_model: ">=2.6.0"   # OK

nozzlenet_model:
  version: "2.6.0"
  requires:
    pipeline: ">=1.6.0"  # ✓ OK

csi_model:
  version: "1.0.0"  # PROBLEM!
  requires:
    pipeline: ">=1.0.0,<1.5.0"  # Incompatible with pipeline 1.6.0!
```
### SBOM.json (Generated Output)

**Location:** Generated during CI, attached to GitHub Releases

**Characteristics:**
- ❌ NOT Git-tracked
- ✅ Machine-readable (JSON/CycloneDX)
- ✅ Comprehensive (includes hashes, dependencies, licenses)
- ✅ For compliance (EU CRA, ISO 26262)

**Generated From:**
- manifest.yaml (component versions)
- File hashes (SHA-256)
- pip freeze (dependencies)

**Example (abbreviated):**

```json
{
  "bomFormat": "CycloneDX",
  "specVersion": "1.5",
  "metadata": {
    "component": {
      "name": "SmartAssist",
      "version": "1.1.0"
    }
  },
  "components": [
    {
      "type": "machine-learning-model",
      "name": "nozzlenet",
      "version": "2.5.4",
      "hashes": [
        {
          "alg": "SHA-256",
          "content": "e3b0c44298fc1c149afbf4c8996fb..."
        }
      ]
    },
    {
      "type": "library",
      "name": "numpy",
      "version": "1.24.0",
      "purl": "pkg:pypi/numpy@1.24.0"
    }
  ]
}
```

### Relationship

```
manifest.yaml (SOURCE)          SBOM.json (GENERATED)
─────────────────────────────────────────────────────
Git-tracked                     NOT Git-tracked
Human-readable                  Machine-readable
Simple (versions only)          Comprehensive (+ hashes, deps, licenses)
Updated on commits              Generated on release
YAML format                     JSON/CycloneDX format

         ↓
    CI reads manifest.yaml
    + Calculates hashes
    + Runs pip freeze
         ↓
    Generates SBOM.json
```

**Not duplicates!** One is source, one is derived output.

---

## ⚡ Quick Reference

### Tag Creation

```bash
# Testing (doesn't trigger CI)
git tag test-feature-x
git push --tags

# Production (triggers CI)
git tag v1.1.0 -m "Release message"
git push --tags
```

### Version Bumping Cheat Sheet

```
Breaking change?              → MAJOR (v2.0.0)
New feature?                  → MINOR (v1.1.0)
Bug fix/improvement?          → PATCH (v1.0.1)
Multiple changes?             → Highest significance wins
```

### CI Behavior

```
Production tag pushed → CI runs full release workflow
Test/dev tag pushed   → CI does nothing
No tag pushed         → CI does nothing
```

### File Locations

```
SmartAssist/
├── manifest.yaml              ← Source of truth (Git-tracked)
├── .github/workflows/
│   └── release.yml            ← Production release CI
└── scripts/
    └── update-manifest.py     ← Manifest updater

Generated (not in Git):
└── SBOM.json                  ← Attached to GitHub Releases
```

### Deployment Verification

```bash
# Download release
wget https://github.com/org/SmartAssist/releases/download/v1.1.0/smartassist-v1.1.0.tar.gz
wget https://github.com/org/SmartAssist/releases/download/v1.1.0/SBOM.json
wget https://github.com/org/SmartAssist/releases/download/v1.1.0/checksums.txt

# Verify integrity
sha256sum -c checksums.txt

# Verify SBOM
cyclonedx validate --input-file SBOM.json

# Deploy
tar -xzf smartassist-v1.1.0.tar.gz
cd SmartAssist
sudo ./install_services.sh
```

---

## 📚 Additional Resources

- **Official SOP:** SSWP-29 (signed by management)
- **Migration Guide:** [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)
- **Repository Structure:** [README.md](README.md)
- **Service Documentation:** [services/README.md](services/README.md)

---

## 🎯 Decision Examples

### Example 1: Model Update

```
Change: nozzlenet 2.5.3 → 2.5.4 (improved accuracy, same interface)

Decision:
├─ Breaking? NO (same input/output format)
├─ New feature? NO (same functionality)
└─ Improvement? YES ✅

Version: 1.0.0 → 1.0.1 (PATCH)
```

### Example 2: Add OTA Feature

```
Change: Add ota-client/, ota-updater/ directories

Decision:
├─ Breaking? NO (old trucks work without OTA)
├─ New feature? YES ✅ (OTA is new)
└─ (skip)

Version: 1.0.1 → 1.1.0 (MINOR)
```

### Example 3: Breaking CAN Change

```
Change: CAN protocol v1 → v2 (incompatible)

Decision:
├─ Breaking? YES ✅ (old trucks can't communicate)
└─ (skip)

Version: 1.1.0 → 2.0.0 (MAJOR)
```

### Example 4: Multiple Changes

```
Changes:
- nozzlenet 2.5.3 → 2.5.4 (fix)
- Add OTA support (feature)
- Fix pipeline bug (fix)

Decision:
├─ Breaking? NO
├─ New feature? YES ✅ (OTA)
└─ (skip)

Version: 1.0.0 → 1.1.0 (MINOR)
Rule: Most significant = MINOR (feature > fixes)
```

---

## 🔄 Workflow Summary

```
Week 1-3: Development
├── Normal commits
├── Test tags (test-*, dev-*)
└── CI: Inactive ✅

Week 4: Release
├── Create production tag (v1.1.0)
├── Push tag
└── CI: Runs full release workflow ✅
    ├── Compares v1.0.0 → v1.1.0
    ├── Updates manifest.yaml
    ├── Generates SBOM.json
    ├── Packages release
    └── Creates GitHub Release
```

---

**Last Updated:** 2025-12-14  
**Maintained By:** Smart Sweeper Team  
**Official Document:** SSWP-29
