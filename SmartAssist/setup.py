"""
SmartAssist Setup Configuration
Enables pip installation: pip install -e .
"""
from setuptools import setup, find_packages
import os

# Read README for long description
def read_file(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return f.read()

# Read requirements
def read_requirements(filename):
    with open(filename, 'r') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]

setup(
    name='smartassist',
    version='1.0.0',
    author='Your Company',
    author_email='dev@company.com',
    description='AI-powered garbage detection system for street sweepers',
    long_description=read_file('README.md'),
    long_description_content_type='text/markdown',
    url='https://github.com/your-org/SmartAssist',
    
    # Package structure
    packages=find_packages(where='pipeline/src') + 
             find_packages(where='models/csi/src') +
             find_packages(where='models/nozzlenet/src') +
             find_packages(where='services/can-server/src'),
    
    package_dir={
        '': 'pipeline/src',
        'models.csi': 'models/csi/src',
        'models.nozzlenet': 'models/nozzlenet/src',
        'services.can_server': 'services/can-server/src'
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
            'smartassist-pipeline=main:main',
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
        '': ['*.yaml', '*.json', '*.txt', '*.md'],
    },
    
    # Zip safety
    zip_safe=False,
)