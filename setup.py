import sys

from setuptools import setup
from setuptools import find_packages

version = '0.0.1'

# Please update tox.ini when modifying dependency version requirements
install_requires = [
    'setuptools>=1.0',
    'six',
    'future',
    'shellescape',
    'asyncio',
    'coloredlogs',
    'ph4-runner>=0.0.5',
    'requests',
    'jsonpath_ng',
    'PyJWT==2.6.0',
    'adafruit-circuitpython-sgp30',
    'adafruit-circuitpython-ahtx0',
    'adafruit-circuitpython-scd4x',
    'adafruit-circuitpython-ccs811',
    'paho-mqtt',
]

dev_extras = [
    'nose',
    'pep8',
    'tox',
    'pypandoc',
]

docs_extras = [
    'Sphinx>=1.0',  # autodoc_member_order = 'bysource', autodoc_default_flags
    'sphinx_rtd_theme',
    'sphinxcontrib-programoutput',
]

try:
    import pypandoc
    long_description = pypandoc.convert_file('README.md', 'rst')
    long_description = long_description.replace("\r", '')

except(IOError, ImportError):
    import io
    with io.open('README.md', encoding="utf-8") as f:
        long_description = f.read()

setup(
    name='ph4-sense',
    version=version,
    description='Sensing lib',
    long_description=long_description,
    url='https://github.com/ph4r05/ph4-sense',
    author='Dusan Klinec',
    author_email='dusan.klinec@gmail.com',
    license='MIT',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],

    packages=find_packages(),
    include_package_data=True,
    install_requires=install_requires,
    extras_require={
        'dev': dev_extras,
        'docs': docs_extras,
    },
    entry_points={
        'console_scripts': [
            'ph4-ups-mon = ph4upsmonit.ups:main',
        ],
    }
)
