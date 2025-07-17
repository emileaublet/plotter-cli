from setuptools import setup, find_packages

setup(
    name="plotter",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "typer",
        "questionary",
        "rich",
        "pyyaml",
    ],
    entry_points={
        "console_scripts": [
            "plotter=cli.commands:app",
        ],
    },
    author="Your Name",
    description="A CLI tool for managing SVG files and paper sizes.",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
)
