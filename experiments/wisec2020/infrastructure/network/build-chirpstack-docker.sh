#!/bin/bash
CHIRPSTACK_NS_VERSION=3.6.0
CHIRPSTACK_AS_VERSION=3.7.0
CHIRPSTACK_GWBRIDGE_VERSION=3.5.0
CHIRPSTACK_GEO_VERSION=3.3.1

set -e

echo "----------------------------------------------------"
echo "Building Network Server v$CHIRPSTACK_NS_VERSION"
echo "----------------------------------------------------"
if [[ ! -d "chirpstack-network-server" ]]; then
    git clone https://github.com/brocaar/chirpstack-network-server.git
fi
cd chirpstack-network-server
git checkout v$CHIRPSTACK_NS_VERSION
docker build -t local/chirpstack-network-server:$CHIRPSTACK_NS_VERSION .
cd ..

echo "----------------------------------------------------"
echo "Building Application Server v$CHIRPSTACK_AS_VERSION"
echo "----------------------------------------------------"
if [[ ! -d "chirpstack-application-server" ]]; then
    git clone https://github.com/brocaar/chirpstack-application-server.git
fi
cd chirpstack-application-server
git checkout v$CHIRPSTACK_AS_VERSION
docker build -t local/chirpstack-application-server:$CHIRPSTACK_AS_VERSION .
cd ..

echo "----------------------------------------------------"
echo "Building Gateway Bridge v$CHIRPSTACK_GWBRIDGE_VERSION"
echo "----------------------------------------------------"
if [[ ! -d "chirpstack-gateway-server" ]]; then
    git clone https://github.com/brocaar/chirpstack-gateway-bridge.git
fi
cd chirpstack-gateway-bridge
git checkout v$CHIRPSTACK_GWBRIDGE_VERSION
docker build -t local/chirpstack-gateway-bridge:$CHIRPSTACK_GWBRIDGE_VERSION .
cd ..

echo "----------------------------------------------------"
echo "Building Geolocation Server v$CHIRPSTACK_GEO_VERSION"
echo "----------------------------------------------------"
if [[ ! -d "chirpstack-geolocation-server" ]]; then
    git clone https://github.com/brocaar/chirpstack-geolocation-server.git
fi
cd chirpstack-geolocation-server
git checkout v$CHIRPSTACK_GEO_VERSION
docker build -t local/chirpstack-geolocation-server:$CHIRPSTACK_GEO_VERSION .
cd ..
