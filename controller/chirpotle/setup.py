from setuptools import setup, find_packages

setup(name='chirpotle',
      version='0.0.1',
      description='A LoRaWAN security evaluation framework',
      author='Frank Hessel',
      author_email='fhessel@seemoo.tu-darmstadt.de',
      packages=find_packages(exclude=['tests','scripts']),
      install_requires=[
        'tpycontrol',     # RPC interface to the nodes
        'bullet',         # CLI node pickers etc.
        'pycryptodomex',  # MAC, MIC, encryption
        'crcmod==1.7',    # CRC calculation (e.g. beacons)
        'gpstime==0.3.3', # timestamps are GPS timestamps
        'colorama==0.4.4',# Colorful text output in scripts
      ],
      scripts=[
        'scripts/beaconclock',
      ],
      zip_safe=False)