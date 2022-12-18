from distutils.core import setup

setup(
    name="pykefcontrol",
    packages=["pykefcontrol"],
    version="0.6.2",
    license="MIT",
    description="Python library for controling the KEF LS50 Wireless II",
    long_description="Python library for controling the KEF LS50 Wireless II. It supports basic commands for setting the volume, the source, and getting the media playing informations",
    author="Robin Dupont",
    author_email="robin.dpnt@gmail.com",
    url="https://github.com/rodupont/pykefcontrol",
    keywords=["Kef", "KEF", "Speaker", "LS50", "LS50W2", "Wireless II", "Wireless 2"],
    install_requires=["requests>=2.26.0", "aiohttp>=3.7.4"],
    classifiers=[
        "Development Status :: 4 - Beta",  # Chose either "3 - Alpha", "4 - Beta" or "5 - Production/Stable" as the current state of your package
        "Topic :: Home Automation",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.4",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
)
