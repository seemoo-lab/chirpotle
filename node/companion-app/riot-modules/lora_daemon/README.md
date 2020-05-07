# Module: lora_daemon

This module controls the lora_modem driver.

It can be controled by commands from various sources (like UART ort network)
depending on the deployment.

## Command Format

Each command consists of a request and a response object. They are represented
as [UBJSON](http://ubjson.org) objects, so they are 1:1 convertible to plain
JSON objects. This allows easy integration with existing tools and protocols on
the command server side, while leaving a little memory and processing footprint
on the node itself.

To send a command to the daemon (which will then pass it to the lora_node), the
following chains of function calls has to be made:

1. Acquire the daemon by calling `lora_daemon_acquire` to use it exclusively.
Then the daemons interface can be used to process 1 request/response pair.
2. Use `lora_daemon_write` to stream the request object into the daemon.
3. Once the write function returns `LORA_DAEMON_WRITE_OK_CMD_BOUNDARY`, the
command boundary has been reached (so a full request object has been parsed),
and the `lora_daemon_read` function can be used to retrieve the response.
4. Finally, release the daemon by calling `lora_daemon_release`, so that the
next command can be processed.

## Basic Structure

The commands here are displayed in normal JSON, as its better readble than
UBJSON and there exists a 1:1 mapping between both dialects.

All request objects follow this structure:

```json
{
  "command_name": {
    "parameter1": "abc",
    "parameter2": 42
  }
}
```

So on the top level, there is only one key that determines the structure of the
inner object. This makes parsing easier, because the first key in the stream
already determines the structure in which to parse the following data.

Each request may either return its specific response object (there may be
response objects that are returned for various request objects), or the generic
error object if some kind of failure occured.

## Request Objects

The following request objects do exist. The headline corresponds to the key of
the top-level object in the JSON structure.

### configure_gain

Configures receiver gain and tx power of the transceiver

Parameters:

| Name             | Type                 | Description
| ---------------- | -------------------- | -------------------------------------
| pwr_out          | 8 bit unsigned int   | Output power in dBm. Application supports 0, 5, 10, 15 or max dBm and will pick the nearest value
| lna_boost        | bool                 | Whether to enable the LNA boost
| lna_gain         | value from 1 to 6    | LNA gain from 1 (highest) to 6 (lowest)

Response Objects:
- [`status`](#status) with code 0 if the command executed successfully.

### fetch_frame

After calling [`receive`](#receive) or enabling the sniffer, the node starts to
write every captured frame into a buffer. `fetch_frame` returns the oldest frame
from this buffer.

If the node receives more frames than the buffer can take, it will start to drop
the oldest frames.

Parameters:

None

Response Objects:
- [`frame_data`](#frame_data) if there was a frame in the buffer
- [`status`](#status) with code 0 if there was no frame.

### get_lora_channel

Returns the current channel configuration of the receiver.

Parameters: None

Response Object: [`lora_channel`](#lora_channel)

### receive

Starts receiving on the currently configured channel. Frames can be polled by
calling [`get_received_frame`](#get_received_frame).

Parameters: None

Response Object: [`status`](#status)

### set_lora_channel

Configures the LoRa channel of the transceiver.

Parameters:

| Name             | Type                 | Description
| ---------------- | -------------------- | -------------------------------------
| frequency        | 32 bit unsigned int  | Center frequency of the channel in Hz
| bandwidth        | 16 bit unsigned int  | Bandwidth in kHz (only 125/250/500)
| codingrate       | 8 bit unsigned int   | Conding rate (5 → 4/5 to 8 → 4/8)
| spreadingfactor  | 8 bit unsigned int   | Spreading factor, 6 to 12
| syncword         | 8 bit unsigned int   | LoRa Syncword. (0x12 / 0x34 for LoRaWAN)

All parameters are optional, missing values will not be changed. However, rx/tx
will be stopped when this command is received, so use
[`get_lora_channel`](#get_lora_channel) to get channel information without
side-effects.


Response Object: lora_channel

### set_preamble_length

Configures the preamble length to use

Parameters:

| Name             | Type                 | Description
| ---------------- | -------------------- | -------------------------------------
| len              | 16 bit unsigned int  | Preamble length in symbols, from 6 to 65535. Modem will add 4.25 symbols internally

Response Object: preamble_length

### standby

Sets the modem to standby state (i.e. stops receiving).

Parameters: None

Response Object: [`status`](#status)

### transmit_frame

Queues a frame for transmission. The modem will be set to standby after
transmission, even if it was receiving before. The frame will be sent on the
channel that is configured at the time of sending, not of queueing!

If no `time` is specified, the frame will be sent as soon as possible.

Parameters:

| Name             | Type                 | Description
| ---------------- | -------------------- | ------------------------------------
| payload          | array of uint8_t     | Payload of the frame
| time             | 64 bit unsigned int  | Time when the frame should be sent, relative to system start

Response Object: [`status`](#status)

## Response Objects

The following request objects do exist. The headline corresponds to the key of
the top-level object in the JSON structure.

### error

The command could not be processed.

| Name             | Type                  | Description
| ---------------- | --------------------- | -----------------------------------
| message          | string (len up to256) | Human-readable error message

### frame_data

Contains a frame that has been received on the node.

| Name           | Type                       | Description
| -------------- | -------------------------- | --------------------------------
| payload        | byte array (len up to 255) | The payload
| has_more       | boolean                    | If there are more frames in the buffer
| frames_dropped | boolean                    | If frames have been dropped between to consecutive fetch_frame calls
| rssi           | integer                    | Frame RSSI in dBm
| snr            | integer                    | Signal to noise ratio
| crc_error      | boolean                    | Transceiver detected CRC error
| time           | 64 bit unsigned int        | Reception time relative to system start

### lora_channel

Returns the current channel configuration.

Values:

| Name             | Type                 | Description
| ---------------- | -------------------- | -------------------------------------
| frequency        | 32 bit unsigned int  | Center frequency of the channel in Hz
| bandwidth        | 16 bit unsigned int  | Bandwidth in kHz (only 125/250/500)
| codingrate       | 8 bit unsigned int   | Conding rate (5 → 4/5 to 8 → 4/8)
| spreadingfactor  | 8 bit unsigned int   | Spreading factor, 6 to 12
| syncword         | 8 bit unsigned int   | LoRa Syncword. (0x12 / 0x34 for LoRaWAN)

### preamble_length

Return value for a preamble length request

Values:

| Name             | Type                 | Description
| ---------------- | -------------------- | -------------------------------------
| len              | 16 bit unsigned int  | The preamble length (without the 4.25 symbols the modem will add)


### status

The command has been processed successfully.

| Name             | Type                  | Description
| ---------------- | --------------------- | -----------------------------------
| message          | string (len up to256) | Human-readable status message
| code             | integer               | Error code. Default = 0 = OK
