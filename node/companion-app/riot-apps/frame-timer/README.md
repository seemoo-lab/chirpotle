# Frame Timer Tool

This RIOT application uses a GPS module and two basic LoRa transceivers to
precisely time the received frames during experiments.

In the given configuration, the following hardware is used:

- A Quectel L80 GPS receiver (the receiver must only provide RMC sentences and
a 1PPS output)
- Two SX1276 LoRa transceivers
- An ESP32 DevBoard (MCU needs 2 serial ports, SPI and interrupts)

## Wiring

For the given configuration, the parts have to be wired as follows:

| ESP32                            | Peripheral                                |
| -------------------------------- | ----------------------------------------- |
| HSPI MISO (GPIO 12)              | First SX1276 MISO                         |
| HSPI MOSI (GPIO 13)              | First SX1276 MOSI                         |
| HSPI CLK (GPIO 14)               | First SX1276 CLK                          |
| HSPI CS (GPIO 15)                | First SX1276 CS                           |
| GPIO 33                          | First SX1276 Reset                        |
| GPIO 32                          | First SX1276 DIO0                         |
| NC                               | First SX1276 DIO3                         |
| HSPI MISO (GPIO 12)              | Second SX1276 MISO                        |
| HSPI MOSI (GPIO 13)              | Second SX1276 MOSI                        |
| HSPI CLK (GPIO 14)               | Second SX1276 CLK                         |
| GPIO 5                           | Second SX1276 CS                          |
| GPIO 27                          | Second SX1276 Reset                       |
| GPIO 19                          | Second SX1276 DIO0                        |
| GPIO 18                          | Second SX1276 DIO3                        |
| GPIO 35 (input only)             | GPS Module 1PPS out                       |
| UART2 RX (GPIO 16)               | GPS Module TX                             |
| UART2 TX (GPIO 17)               | GPS Module RX                             |

## Testing rx2 capture

The app is able to automatically capture the RX2 window in the ADR Wormhole
experiment by searching for two consecutive uplinks of the same payload followed
by a downlink. It then switches quickly to the rx2 channel with the radio that
usually follows the uplink.

This can be tested with TPy LoRa for a given node `l`:

```python

l.set_lora_channel(frequency=868300000,invertiqtx=True,
  spreadingfactor=12,syncword=0x34)
l.transmit_frame(list(range(13))), blocking=True)
time.sleep(0.5)
l.transmit_frame(list(range(13))), blocking=True)
time.sleep(0.9)
l.set_lora_channel(invertiqtx=False)
time.sleep(0.1)
l.transmit_frame(list(range(12))), blocking=True)
time.sleep(0.1)
l.set_lora_channel(frequency=869525000)
time.sleep(0.1)
l.transmit_frame(list(range(12)))

```
