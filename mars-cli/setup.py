from setuptools.command.install import install
from _version import __version__
from setuptools import find_packages, setup
import pathlib
import os

with open("requirements.txt", "r") as file:
    required_deps = file.read().splitlines()

parent_folder = pathlib.Path(__file__).parent.resolve()
long_description = (parent_folder / "README.md").read_text(encoding="utf-8")


class custom_install(install):
    def run(self):
        # Default install command
        install.run(self)

        os.system("python3 generate_config.py")


setup(
    name="mars",
    cmdclass={
        "install": custom_install,
    },
    description="Multi-omics Adapter for Repository Submissions",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(include=["mars_lib"]),
    py_modules=["mars_cli"],
    version=__version__,
    license="MIT",
    install_requires=[required_deps],
    extras_require={
        "test": [
            # Dependencies for testing only
            "black",
            "ruff",
            "pytest",
            "pytest-cov",
        ]
    },
    project_urls={
        "Source": "https://github.com/elixir-europe/MARS",
        "Bug Reports": "https://github.com/elixir-europe/MARS/issues",
    },
    entry_points={  # Optional
        "console_scripts": [
            "mars-cli=mars_cli:main",
        ],
    },
    python_requires=">=3.9, <4",
)
