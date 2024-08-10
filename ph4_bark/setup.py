from setuptools import find_packages, setup

version = "0.0.1"

# Please update tox.ini when modifying dependency version requirements
install_requires = [
    "setuptools>=1.0",
    "six",
    "future",
    "coloredlogs",
    "pyaudio",
    "librosa",
    "sounddevice",
    "numpy<2",
    "paho-mqtt",
]

dev_extras = [
    "nose",
    "pep8",
    "tox",
    "pypandoc",
]

test_extras = [
    "pre-commit",
    "pytest",
    "mypy",
    "types-ujson",
]

docs_extras = [
    "Sphinx>=1.0",  # autodoc_member_order = 'bysource', autodoc_default_flags
    "sphinx_rtd_theme",
    "sphinxcontrib-programoutput",
]

try:
    import pypandoc

    long_description = pypandoc.convert_file("README.md", "rst")
    long_description = long_description.replace("\r", "")

except (IOError, ImportError):
    import io

    with io.open("README.md", encoding="utf-8") as f:
        long_description = f.read()

setup(
    name="ph4-bark",
    version=version,
    description="Sensing lib",
    long_description=long_description,
    url="https://github.com/ph4r05/ph4-sense",
    author="Dusan Klinec",
    author_email="dusan.klinec@gmail.com",
    license="MIT",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.10",
    ],
    packages=find_packages(
        include=[
            "ph4_sense",
            "ph4_sense.*",
            "ph4_sense_py",
            "ph4_sense_py.*",
        ]
    ),
    include_package_data=True,
    install_requires=install_requires,
    extras_require={
        "dev": dev_extras,
        "test": test_extras,
        "docs": docs_extras,
    },
    entry_points={
        "console_scripts": [
            "ph4-bark = ph4_bark.bark:main",
        ],
    },
)
