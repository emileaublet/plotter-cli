from setuptools import setup, find_packages

# Note: Dependencies are now specified in pyproject.toml
# This setup.py is kept for backward compatibility
# For modern builds, use: pip install -e .

setup(
    name="plotter",
    version="1.0.0",
    packages=find_packages(),
    # install_requires moved to pyproject.toml - don't specify here
    entry_points={
        "console_scripts": [
            "plotter=plotter_cli.commands:app",
        ],
    },
    author="Your Name",
    description="A CLI tool for managing SVG files and paper sizes.",
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
    package_data={
        "plotter_cli": [
            "settings.yaml",
            ".vpype.toml",
            "gui/templates/*.html",
            "gui/static/*.js",
            "gui/static/*.css",
        ],
    },
    include_package_data=True,
)
