import os

from setuptools import setup

version_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), "freecad", "maxproframe", "version.py")
with open(version_path) as fp:
    exec(fp.read())

setup(
    name="maxproframe",
    version=str(__version__),
    packages=["freecad", "freecad.maxproframe", "freecad.frameforge"],
    maintainer="Vivien HENRY",
    maintainer_email="vivien.henry@inductivebrain.fr",
    url="https://github.com/sclMAX/MaxProFrame",
    description="MaxProFrame is dedicated to creating Frames, Profiles and Beams, and applying operations (miter cuts, trim cuts, custom sketch profiles, portable libraries) in FreeCAD.",
    include_package_data=True,
)
