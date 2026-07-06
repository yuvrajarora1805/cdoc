from setuptools import setup
from Cython.Build import cythonize

# This script will compile run_carm_viewer.py into a C extension (.pyd)
# Usage: python setup_cython.py build_ext --inplace

setup(
    ext_modules=cythonize(
        ["run_carm_viewer.py"],
        compiler_directives={'language_level': "3"}
    )
)
