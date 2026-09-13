from setuptools import setup, find_packages

setup(
    name="publisher-daemon",
    version="0.1.0",
    description="Shared publishing logic for Hugo sites on Workbench",
    author="Mark Groves",
    license="MIT",
    packages=find_packages(),
    python_requires=">=3.11",
    install_requires=[
        "Pillow>=12.0.0",
    ],
)
