#!/usr/bin/env python3
"""
SmartAssist Installation Validation Script

Tests all dependencies and verifies the installation is correct.

USAGE:
    python3 validate_installation.py [--verbose] [--skip-nvidia]

EXIT CODES:
    0 - All tests passed
    1 - One or more tests failed
"""

import argparse
import sys
import os
import subprocess
from pathlib import Path

# Colors for output
class Colors:
    GREEN = '\033[0;32m'
    RED = '\033[0;31m'
    YELLOW = '\033[1;33m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color


class ValidationTest:
    """Represents a single validation test"""
    
    def __init__(self, name, description):
        self.name = name
        self.description = description
        self.passed = False
        self.error = None


def print_header(text):
    """Print section header"""
    print(f"\n{Colors.BLUE}{'='*60}{Colors.NC}")
    print(f"{Colors.BLUE}{text}{Colors.NC}")
    print(f"{Colors.BLUE}{'='*60}{Colors.NC}\n")


def print_test(test, result, message=""):
    """Print test result"""
    status = f"{Colors.GREEN}✓ PASS{Colors.NC}" if result else f"{Colors.RED}✗ FAIL{Colors.NC}"
    print(f"{status} | {test}")
    if message:
        print(f"       {message}")


def run_command(cmd, capture=True, timeout=5):
    """
    Run a shell command
    
    Returns:
        tuple: (success: bool, output: str)
    """
    try:
        if capture:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return result.returncode == 0, result.stdout.strip()
        else:
            result = subprocess.run(cmd, shell=True, timeout=timeout)
            return result.returncode == 0, ""
    except subprocess.TimeoutExpired:
        return False, "Timeout"
    except Exception as e:
        return False, str(e)


def test_python_version():
    """Test Python version"""
    test = ValidationTest("Python 3.8+", "Check Python version")
    
    success, output = run_command("python3 --version")
    if success:
        version = output.replace("Python ", "")
        major, minor = version.split('.')[:2]
        if int(major) >= 3 and int(minor) >= 8:
            test.passed = True
            print_test(f"Python {version}", True)
        else:
            print_test(f"Python {version} (need 3.8+)", False)
    else:
        print_test("Python", False, "Python 3 not found")
    
    return test


def test_python_package(package_name, import_name=None):
    """Test if Python package is installed"""
    if import_name is None:
        import_name = package_name
    
    test = ValidationTest(f"Python: {package_name}", f"Import {import_name}")
    
    try:
        __import__(import_name)
        version = ""
        try:
            mod = __import__(import_name)
            if hasattr(mod, '__version__'):
                version = f" ({mod.__version__})"
        except:
            pass
        
        test.passed = True
        print_test(f"{package_name}{version}", True)
    except ImportError:
        print_test(package_name, False, f"Not installed (pip install {package_name})")
    
    return test


def test_gstreamer():
    """Test GStreamer installation"""
    test = ValidationTest("GStreamer", "Check GStreamer tools")
    
    success, output = run_command("gst-inspect-1.0 --version")
    if success:
        test.passed = True
        version = output.split('\n')[0] if output else "installed"
        print_test(f"GStreamer {version}", True)
    else:
        print_test("GStreamer", False, "gst-inspect-1.0 not found")
    
    return test


def test_gstreamer_python():
    """Test GStreamer Python bindings"""
    test = ValidationTest("GStreamer Python", "Check Python bindings")
    
    try:
        import gi
        gi.require_version('Gst', '1.0')
        from gi.repository import Gst
        Gst.init(None)
        test.passed = True
        print_test("GStreamer Python bindings", True)
    except Exception as e:
        print_test("GStreamer Python bindings", False, str(e))
    
    return test


def test_deepstream(skip_nvidia=False):
    """Test DeepStream installation"""
    if skip_nvidia:
        print_test("DeepStream (skipped)", True)
        test = ValidationTest("DeepStream", "Skipped")
        test.passed = True
        return test
    
    test = ValidationTest("DeepStream", "Check DeepStream SDK")
    
    success, output = run_command("deepstream-app --version")
    if success:
        test.passed = True
        print_test(f"DeepStream", True, output)
    else:
        print_test("DeepStream", False, "deepstream-app not found")
    
    return test


def test_pyds(skip_nvidia=False):
    """Test PyDS (DeepStream Python bindings)"""
    if skip_nvidia:
        print_test("PyDS (skipped)", True)
        test = ValidationTest("PyDS", "Skipped")
        test.passed = True
        return test
    
    test = ValidationTest("PyDS", "DeepStream Python bindings")
    
    try:
        import pyds
        version = getattr(pyds, '__version__', 'installed')
        test.passed = True
        print_test(f"PyDS {version}", True)
    except ImportError:
        print_test("PyDS", False, "Not installed (install DeepStream Python bindings)")
    
    return test


def test_can_utils():
    """Test CAN utilities"""
    test = ValidationTest("CAN Utils", "Check CAN tools")
    
    success, _ = run_command("candump --help", capture=False)
    if success:
        test.passed = True
        print_test("CAN utilities", True)
    else:
        print_test("CAN utilities", False, "candump not found (sudo apt-get install can-utils)")
    
    return test


def test_smartassist_imports():
    """Test SmartAssist imports"""
    test = ValidationTest("SmartAssist", "Import pipeline modules")
    
    try:
        # Try to import from pipeline
        sys.path.insert(0, str(Path(__file__).parent.parent))
        
        from pipeline.utils import paths
        from pipeline.utils import config
        
        test.passed = True
        print_test("SmartAssist imports", True)
    except Exception as e:
        print_test("SmartAssist imports", False, str(e))
    
    return test


def test_directory_structure():
    """Test directory structure"""
    test = ValidationTest("Directory Structure", "Check required directories")
    
    root = Path(__file__).parent.parent
    required_dirs = [
        'pipeline/src',
        'pipeline/config',
        'models/csi/src',
        'models/nozzlenet/src',
        'services/can-server/src',
    ]
    
    missing = []
    for dir_path in required_dirs:
        if not (root / dir_path).exists():
            missing.append(dir_path)
    
    if not missing:
        test.passed = True
        print_test("Directory structure", True)
    else:
        print_test("Directory structure", False, f"Missing: {', '.join(missing)}")
    
    return test


def test_model_weights():
    """Test model weights existence"""
    test = ValidationTest("Model Weights", "Check model files")
    
    root = Path(__file__).parent.parent
    model_dirs = [
        'models/csi/weights/v1.0.0',
        'models/nozzlenet/weights/v2.5.3',
    ]
    
    missing = []
    for dir_path in model_dirs:
        model_dir = root / dir_path
        if not model_dir.exists():
            missing.append(dir_path)
        elif not any(model_dir.glob('*.plan')):
            missing.append(f"{dir_path} (no .plan files)")
    
    if not missing:
        test.passed = True
        print_test("Model weights", True)
    else:
        print_test("Model weights", False, f"Missing: {', '.join(missing)}")
    
    return test


def main():
    """Main validation"""
    parser = argparse.ArgumentParser(description='Validate SmartAssist installation')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--skip-nvidia', action='store_true', help='Skip NVIDIA-specific tests')
    args = parser.parse_args()
    
    print_header("SmartAssist Installation Validation")
    
    tests = []
    
    # Python version
    print_header("Python Environment")
    tests.append(test_python_version())
    
    # Python packages
    tests.append(test_python_package('numpy'))
    tests.append(test_python_package('yaml', 'yaml'))
    tests.append(test_python_package('pandas'))
    tests.append(test_python_package('cv2', 'cv2'))
    tests.append(test_python_package('can'))
    tests.append(test_python_package('cantools'))
    
    # GStreamer
    print_header("GStreamer")
    tests.append(test_gstreamer())
    tests.append(test_gstreamer_python())
    
    # NVIDIA
    if not args.skip_nvidia:
        print_header("NVIDIA Components")
        tests.append(test_deepstream(args.skip_nvidia))
        tests.append(test_pyds(args.skip_nvidia))
    
    # System utilities
    print_header("System Utilities")
    tests.append(test_can_utils())
    
    # SmartAssist
    print_header("SmartAssist")
    tests.append(test_directory_structure())
    tests.append(test_smartassist_imports())
    tests.append(test_model_weights())
    
    # Summary
    print_header("Summary")
    
    passed = sum(1 for t in tests if t.passed)
    total = len(tests)
    
    print(f"Tests passed: {passed}/{total}")
    
    if passed == total:
        print(f"\n{Colors.GREEN}✓ All tests passed!{Colors.NC}\n")
        return 0
    else:
        failed_tests = [t for t in tests if not t.passed]
        print(f"\n{Colors.RED}✗ {len(failed_tests)} test(s) failed:{Colors.NC}")
        for t in failed_tests:
            print(f"  - {t.name}")
        print()
        return 1


if __name__ == '__main__':
    sys.exit(main())