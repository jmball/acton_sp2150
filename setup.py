import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="acton_sp2150",
    use_scm_version=True,
    setup_requires=["setuptools_scm"],
    author="James Ball",
    author_email="",
    description="Princeton Instruments Acton SP2150 monochromator control library",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/jmball/acton_sp2150",
    py_modules=["sp2150"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GPL-3.0",
        "Operating System :: OS Independent",
    ],
)
