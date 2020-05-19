# Network Infrastructure

This README will give you a brief overview of the steps required to create the basic network infrastructure to run the experiments.
You will install a ChirpStack network server via Docker and learn how to add gateways to it.

> **Note:** This is the absolute minimum to get the server running. This server is **not secured** in any way and should only be used in a trusted network for testing and development.

## Environment

In the following, we assume you have a test machine running Debian Buster, and a user called `chirpotle` which is in groups `sudo` and `docker`:

```bash
useradd -m chirpotle
usermod -aG sudo,docker chirpotle
```

Clone the repository (we clone it to the desktop in this case):

```bash
# as user chirpotle:
git clone https://github.com/seemoo-lab/chirpotle.git
```

## Setup Docker and Docker Compose

Install Docker according to the official documentation: https://docs.docker.com/engine/install/debian/

After that, install Docker Compose: https://docs.docker.com/compose/install/#install-compose-on-linux-systems

We assume the binary is in `/usr/local/bin/docker-compose`.

## Building the ChirpStack Docker Images

Build the required Docker images locally. We provide a script for that:

```bash
cd ~/Desktop/chirpotle/experiments/wisec2020/infrastructure/network
./build-chirpstack-docker.sh
```

The config has been changed to allow persistence, therefore you need to create two volumes:

```bash
sudo docker volume create --driver local loraserver-postgresqldata
sudo docker volume create --driver local loraserver-redisdata
```

You can test if the server works by calling:

```bash
# in /home/chirpotle/Desktop/chirpotle/experiments/wisec2020/infrastructure/network/chirpstack/
sudo docker-compose up
```

Open your browser and point it to http://localhost:8080 (Credentials: admin/admin).

## ChirpStack via systemd

To use ChirpStack as a service, create the file `/etc/systemd/system/chirpstack.service` with the following content.
You may need to adjust the location of docker-compose and the repository location (here, it is cloned to `/home/chirpotle/Desktop/chirpotle`).

```ini
[Unit]
Description=ChirpStack on Port 8080
Requires=docker.service
Requires=networking.service
After=docker.service

[Service]
Restart=always
User=chirpotle
Group=docker
WorkingDirectory=/home/chirpotle/Desktop/chirpotle/experiments/wisec2020/infrastructure/network/chirpstack
# Shutdown container (if running) when unit is stopped
ExecStartPre=/usr/local/bin/docker-compose -f /home/chirpotle/Desktop/chirpotle/experiments/wisec2020/infrastructure/network/chirpstack/docker-compose.yml down
# Start container when unit is started
ExecStart=/usr/local/bin/docker-compose -f /home/chirpotle/Desktop/chirpotle/experiments/wisec2020/infrastructure/network/chirpstack/docker-compose.yml up
# Stop container when unit is stopped
ExecStop=/usr/local/bin/docker-compose -f /home/chirpotle/Desktop/chirpotle/experiments/wisec2020/infrastructure/network/chirpstack/docker-compose.yml down

[Install]
WantedBy=multi-user.target
```

Then register the service and start it (stop the container first if you ran it directly above):

```bash
sudo systemctl enable chirpstack
sudo systemctl start chirpstack
```

## Clean up

Clean up the tempoarary images and containers:

```bash
sudo docker system prune
```

## Configure the Server

Start the service and open the default URL in the browser: http://localhost:8080 Log in as `admin` with password `admin`

**Creating a network server:** Go to *Network Servers* → *Add* and enter the following data (fields that aren't mentioned can stay on their default value):

* Network Server Name (human-readble): `Default Network Server`
* Network Server Name (hostname): `loraserver:8000`

**Creating a gateway profile:** Go to *Gateway Profiles* → *Create* and enter:

* Name: `Default Gateway Profile`
* Enabled Channels: `0,1,2`
* Network Server: `Default Network Server`

**Creating a service profile:** Go to *Service Profiles* → *Create* and enter:

* Service-Profile Name: `Default Service Profile`
* Network Server: `Default Network Server`
* Add Gateway Meta-Data: `true`
* Minimum Allowed Data Rate: `0`
* Maximum Allowed Data Rate: `5`

**Create a device profile for class A:** Go to *Device Profiles* → *Create* and enter:

* General
   * Device-Profile Name: `Class A (ABP)`
   * LoRaWAN MAC Version: `1.1.0`
   * LoRaWAN Regional Parameters Revision: `B`
* Join (OTAA/ABP)
   * Device Supports OTAA: `false`
   * RX1 Delay: `1`
   * RX1 Data Rate Offset: `0`
   * RX2 Data Rate: `0`
   * RX2 Channel Frequency: `869525000`
   * Factory-Preset Frequencies: `868100000,868300000,868500000`

**Create a device profile for class B:** Go to *Device Profiles* → *Create* and enter:

* General
   * Device-Profile Name: `Class B (ABP)`
   * LoRaWAN MAC Version: `1.1.0`
   * LoRaWAN Regional Parameters Revision: `B`
* Join (OTAA/ABP)
   * Device Supports OTAA: `false`
   * RX1 Delay: `1`
   * RX1 Data Rate Offset: `0`
   * RX2 Data Rate: `0`
   * RX2 Channel Frequency: `869525000`
   * Factory-Preset Frequencies: `868100000,868300000,868500000`
* Class-B
   * Device Supports Class B: `true`
   * Class-B Ping-Slot Periodicity: `every 32 seconds`
   * Class-B Ping-Slot Data Rate: `3`
   * Class-B Ping-Slot Frequency: `869525000`

After creating both device profiles, return to the device profile list and navigate again into the device profiles.
You will see the internal ID of the device profiles in the URL.
This internal ID is needed for the experiments and has to be entered in the `testrunner.py` scripts in the definition of `DUT_CS_ED`.
Otherwise, the test automation is not able to create the devices with the right profiles.
Use the ID of the Class A device for ADR spoofing and the Class B device profile ID for beacon spoofing.

**Create an application:** Go to *Applications* → *Create* and enter:

* Application Name: `Default-Application`
* Application Description: `default application for testing`
* Service Profile: `Default Service Profile`

In theory, you would again need to revisit the application details page and note down the application ID to enter it in the `DUT_CS_ED` definition.
However, if you have only one application, this ID will be `1`, which is already configured there.

The setup and configuration of the server is now complete.

## Registering a Gateway

In order to receive and transmit messages, at least one gateway must be added to the network server.

The process depends on the specific gateway hardware, so we only summarize the most important steps based on the [Dragino PG1301](https://www.dragino.com/products/lora/item/149-lora-gps-hat.html) that we used.
As this board does not connect the PPS output of the GPS module to the PPS input of the SX1301 concentrator chip and the Quectel L70 GPS module does not generate the ublox sentences required by the default forwarder software, we customized the forwarder to be able to use GPS and beaconing.

To download, build and package the forwarder, run the following code on the Raspberry Pi:

```bash
git clone https://github.com/dragino/pi_gateway_fwd.git
cd dragino_pi_gateway_fwd.git
git checkout fix/gpstime-without-pps
make all deb
sudo dpkg -i lorapktfwd.deb
```

The global configuration in `/etc/lora-gateway/global_conf.json` can be overriden with a file called `local_conf.json` in the same directory. In our case, it has the following content to enable beaconing and GPS-synchronization:

```json
{
    "gateway_conf": {
        "gateway_ID": "ABCDEFABCDEFFFFF",
        "server_address": "192.168.42.1",
        "gps": true,
        "gps_tty_path": "/dev/ttyS0",
        "gps_pps_path": "/dev/gpiochip0",
        "gps_pps_line": 18,
        "forward_crc_error": true,
        "forward_crc_disabled": true,
        "logdebug": 5,
        "beacon_period": 128,
        "beacon_freq_hz": 869525000,
        "beacon_datarate": 9,
        "beacon_bw_hz": 125000,
        "beacon_power": 14,
        "beacon_infodesc": 0
    }
}
```

Note that the `gps_pps_path` and `gps_pps_line` are only needed for our GPS workaround, if you have a gateway without the mentioned issue, you probably only need to enable GPS.
Also check the IP (so that it is pointing to the machine running your network server) and assure that the gateway ID is unique (a good idea is using the Ethernet MAC address as prefix and appending `FFFF`).

After changing the config, restart the service by executing:

```bash
sudo systemctl restart lorapktfwd
```

Make sure to run `raspi-config` to enable SPI and make the serial connection available for custom use (*not* for login shell etc.).
If you have installed `python3-serial`, you can test the GPS module via `miniterm.py /dev/ttyS0 9600`, you should see the NMEA sentences.

**Add Gateway to ChirpStack:** In the web interface, click *Gateways* → *Create* and enter:

* Gateway Name: `Gateway-01`
* Gateway Description: `Raspberry Pi Gateway`
* Gateway ID: *the ID from the config file*
* Network Server: `Default Network Server`

If everything worked well, the "last seed" entry in the gateway list should update within a few minutes.

With this, your LoRaWAN network for testing is ready.
