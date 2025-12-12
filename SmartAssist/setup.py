"""
SmartAssist Setup Configuration
Enables pip installation: pip install -e .

FIXED: Proper package structure that allows imports like:
    from pipeline.utils import paths
    from models.nozzlenet.state_machine import SmartStateMachine
"""
from setuptools import setup
import os

# Read README for long description
def read_file(filename):
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return f.read()
    except:
        return ''

# Read requirements
def read_requirements(filename):
    try:
        with open(filename, 'r') as f:
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except:
        return []

setup(
    name='smartassist',
    version='1.0.0',
    author='Your Company',
    author_email='dev@company.com',
    description='AI-powered garbage detection system for street sweepers',
    long_description=read_file('README.md'),
    long_description_content_type='text/markdown',
    url='https://github.com/your-org/SmartAssist',
    
    # FIXED: Explicit package list with proper structure
    packages=[
        # Pipeline packages
        'pipeline',
        'pipeline.utils',
        'pipeline.camera',
        'pipeline.can',
        'pipeline.monitoring',
        'pipeline.pipeline',
        # Model packages  
        'models',
        'models.csi',
        'models.nozzlenet',
        # Service packages
        'services',
        'services.can_server',
    ],
    
    # FIXED: Proper package directory mapping
    package_dir={
        'pipeline': 'pipeline/src',
        'pipeline.utils': 'pipeline/src/utils',
        'pipeline.camera': 'pipeline/src/camera',
        'pipeline.can': 'pipeline/src/can',
        'pipeline.monitoring': 'pipeline/src/monitoring',
        'pipeline.pipeline': 'pipeline/src/pipeline',
        'models': 'models',
        'models.csi': 'models/csi/src',
        'models.nozzlenet': 'models/nozzlenet/src',
        'services': 'services',
        'services.can_server': 'services/can-server/src',
    },
    
    # Dependencies
    install_requires=read_requirements('requirements.txt'),
    
    # Optional dependencies
    extras_require={
        'dev': [
            'pytest>=7.0.0',
            'pytest-cov>=3.0.0',
            'black>=22.0.0',
            'flake8>=4.0.0',
            'mypy>=0.950'
        ],
    },
    
    # Entry points
    entry_points={
        'console_scripts': [
            'smartassist-pipeline=pipeline.main:main',
            'smartassist-can-server=services.can_server.main:main',
        ],
    },
    
    # Classifiers
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Topic :: Scientific/Engineering :: Artificial Intelligence',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
    ],
    
    # Python version requirement
    python_requires='>=3.8',
    
    # Include additional files
    include_package_data=True,
    package_data={
        'pipeline': ['*.yaml', '*.json', '*.txt'],
        'models.csi': ['*.yaml', '*.txt'],
        'models.nozzlenet': ['*.yaml', '*.txt'],
    },
    
    # Zip safety
    zip_safe=False,
)