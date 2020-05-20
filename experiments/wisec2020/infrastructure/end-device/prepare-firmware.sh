#!/bin/bash

set -e

# Clone the official repo
if [[ ! -d LoRaMac-node ]]; then
    git clone https://github.com/Lora-net/LoRaMac-node.git
    cd LoRaMac-node
    git config commit.gpgSign false
    git config core.autocrlf true
else
    cd LoRaMac-node
fi

# If the wisec2020 branch does not exist yet, create it.
if ! git branch --list | grep "wisec2020"; then
    # branch from the commit that we based our modifications on (current 5.0.0 feature branch at the time of writing)
    git branch wisec2020 92e37147
    git checkout wisec2020
    git am --ignore-space-change --ignore-whitespace ../patches/*.patch
else
    git checkout wisec2020
fi

# Initialize the repo's submodules
git submodule update --init

mkdir -p build

# Build the app for adr spoofing
cd build
cmake -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_TOOLCHAIN_FILE="../cmake/toolchain-arm-none-eabi.cmake" \
        -DAPPLICATION="LoRaMac" \
        -DSUB_PROJECT="classA" \
        -DDISABLE_LINK_ADR_NB_REP="ON" \
        -DCLASSB_ENABLED="OFF" \
        -DACTIVE_REGION="LORAMAC_REGION_EU868" \
        -DREGION_EU868="ON" \
        -DREGION_US915="OFF" \
        -DREGION_CN779="OFF" \
        -DREGION_EU433="OFF" \
        -DREGION_AU915="OFF" \
        -DREGION_AS923="OFF" \
        -DREGION_CN470="OFF" \
        -DREGION_KR920="OFF" \
        -DREGION_IN865="OFF" \
        -DREGION_RU864="OFF" \
        -DBOARD="NucleoL476" \
        -DMODULATION="LORA" \
        -DMBED_RADIO_SHIELD="SX1276MB1MAS" ..
make

# build the app for beacon spoofing
cmake -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_TOOLCHAIN_FILE="../cmake/toolchain-arm-none-eabi.cmake" \
        -DAPPLICATION="LoRaMac" \
        -DSUB_PROJECT="classB" \
        -DDISABLE_LINK_ADR_NB_REP="OFF" \
        -DCLASSB_ENABLED="ON" \
        -DACTIVE_REGION="LORAMAC_REGION_EU868" \
        -DREGION_EU868="ON" \
        -DREGION_US915="OFF" \
        -DREGION_CN779="OFF" \
        -DREGION_EU433="OFF" \
        -DREGION_AU915="OFF" \
        -DREGION_AS923="OFF" \
        -DREGION_CN470="OFF" \
        -DREGION_KR920="OFF" \
        -DREGION_IN865="OFF" \
        -DREGION_RU864="OFF" \
        -DBOARD="NucleoL476" \
        -DMODULATION="LORA" \
        -DMBED_RADIO_SHIELD="SX1276MB1MAS" ..
make

# Write some info to the CLI on where to find the binaries
cat <<EOF

Building the firmware was successful. To flash the binaries to the L476
DevBoard, you need to copy them to the virtual mass storage device.
The binaries are located as follows:

ADR-Spoofing:
  $(pwd)/src/apps/LoRaMac/LoRaMac-classA.bin

Beacon Spoofing:
  $(pwd)/src/apps/LoRaMac/LoRaMac-classB.bin

For device addresses and keys, see
  LoRaMac-node/src/apps/LoRaMac/class{A,B}/NucleoL476/Commissioning.h
Run this script again after modifying the values.

EOF
