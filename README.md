![ChirpOTLE](assets/chirpotle.png)

ChirpOTLE is a practical LoRaWAN security evaluation framework that provides tools for the deployment and management of a LoRa testbed based on COTS hardware.
It allows managing LoRa field nodes from a central controller and to orchestrate experiments and tests using a Python 3 interface.

By collocating the nodes with a LoRaWAN network, the built-in functions for receiving, transmitting, jamming, and sniffing can be used to study their effects on the network under test.
With its dissector and predefined building blocks like wormholes, the framework allows for quick vulnerability assessment in LoRaWAN networks as well as for the evaluation of attempts for their mitigation.

## Basic Setup

The framework is managed through the `chirpotle.sh` shell script.
It creates and manages a virtual environment, node configurations and it takes care of creating the RPC stubs for communication with the nodes.

To get started with the controller, just run the `install` task and you are ready to go:

```bash
./chirpotle.sh install
```

If you want to be able to use the framework independent of the working directory, you can add it to your `.bashrc`:

```bash
echo "alias chirpotle=\"$(pwd)/chirpotle.sh\" \"\$@\"" >> ~/.bashrc
```

You will then be able to call it from any directory like:

```bash
chirpotle interactive
```

By default, the virtual environment is created in the `env` folder in the repository and the configurations are stored in `conf`.
If you want a clean install, you can delete the `env` folder without losing your configuration.

## Configure Your Setup

As ChirpOTLE is meant to be deployed in the field, it uses a star topology with the controller in the center and nodes in the field.
Controller and field nodes are connected through **SSH for deployment** and **RPC calls** for control during experiments.

> **Note:** The tool assumes a secure network connection between controller and nodes, the RPC traffic is not secured and SSH host keys are trusted by default.

For this description, we assume you have the following setup:

- The controller is running on your desktop machine, and you've installed ChirpOTLE as mentioned [above](#basic-setup)
- You have two Raspberry Pis running a fresh installation of Raspbian, and they are available as loranode1.example and loranode2.example
- To each of the Pis, you've got a [LoPy 4](https://docs.pycom.io/datasheets/development/lopy4/) connected via a USB-to-Serial bridge, so it's available as `/dev/ttyUSB0`

> **Note:** Other LoRa hardware can be used with the framework, see [`Makefile.preconf` of the companion application](node/companion-app/riot-apps/chirpotle-companion/Makefile.preconf) for more options.

### Prepare the Nodes

First, you need to make the nodes available for root access via SSH.
Copy your SSH key to `/root/.ssh/authorized_keys` on each of the Raspberry Pis.

> **Note:** Your SSH public key is usually located in `~/.ssh/id_rsa.pub`. If that file does not exist, run `ssh-keygen -t rsa -b 4096` on your desktop machine.

After having deployed the keys, you can start installing Python 3 and pip on the Pis.
All other software installation will be managed by the framework.

```bash
ssh root@loranode1.example apt-get update
ssh root@loranode2.example apt-get update
ssh root@loranode1.example apt-get install python3 python3-pip
ssh root@loranode2.example apt-get install python3 python3-pip
```

### Create a Configuration

Now it is time to setup the configuration, so that your controller knows which nodes are avaialble.

All configurations are stored in the `conf` folder of the repository after running `chirpotle.sh install`, but the easiest way for most cases is to use the interactive editor.

Run `./chirpotle.sh confeditor`, and you'll be greeted with the main menu:

```bash
What do you want to do?
        
   📝  List/edit controller configurations 
   📝  List/edit node profiles
   Save changes and quit 
```

- Select `List/edit controller configuration`.
- Select `Create new configuration`
- Enter the name `testconf`
- Select `Add Node`
   - Name: `alice` (This is how you will address the node in scripts)
   - Host: `loranode1.example`
   - Node profile: `uart-lopy4`
- Select `Add Node`
   - Name: `bob` (This is how you will address the node in scripts)
   - Host: `loranode2.example`
   - Node profile: `uart-lopy4`

Your configuration should now look like this:

```
   🖥️  Node: alice (loranode1.example, uart-lopy4) 
   🖥️  Node: bob (loranode2.example, uart-lopy4) 
   ➕ Add node                                          
   🏷️  Rename this confiugration                       
   Delete this configuration                           
   Go back 
```

If everything seems alright, select `go back` in all menus, and your configuration will be saved as `testconf`.

### Deploy ChirpOTLE to the Nodes

Now, you can test if everything is set up correctly and if the nodes have all required software installed:

```bash
./chirpotle.sh deploycheck --conf conftest
```

> **Note:** Most of the CLI commands support the `--conf` option to select the configuration that you want to use.
If you omit this option, the CLI will try to use a configuration with the name `default`.

You should now see green checkmarks for everything that is working, a warning sign for optional software that is not required in every case and a red x for unfulfilled requirements.
If you see errors, please re-check the instructions above.

If all requirements are fulfilled, you can start deploying ChirpOTLE to the nodes:

```bash
./chirpotle.sh deploy --conf conftest
```

This command will do the following:

- Build and bundle the TPy node in `submodules/tpy/node`
- Bundle the add additional ChirpOTLE modules in `node/remote-modules`
- Build and bundle the companion application for the remote MCUs from `node/companion-app`
- For each node:
   - Copy everything to the nodes
   - Install additional software (globally, using pip)
   - If MCUs are connected to the nodes (the LoPy 4 boards in this case): Flash the MCUs with the companion application

### Start the Nodes

As a last step before starting with experiments, you need to launch the node deamon on each node:

```bash
./chirpotle.sh restartnodes --conf conftest
```

Now you should be ready to go!

## Getting Started

To familiarize with the framework, the best way is to start an interactive session.
After you have set everything up, you can run the `interactive` task to start such a session:

```bash
./chirpotle.sh interactive --conf testconf
```

If you used the setup mentioned above, you can now try to communicate between both LoRa boards:

```python
# Assure both use the same channel setup
bob_lora.set_lora_channel(**alice_lora.get_lora_channel())

# Configure IQ inversion to default values
alice_lora.set_lora_channel(invertiqtx=True)
bob_lora.set_lora_channel(invertiqrx=False)

# Set Bob in receive mode
bob_lora.receive()

# Transmit a frame
alice_lora.transmit_frame([int(b) for b in b'Hello, World'])

# Check if Bob received it
bobframe = bob_lora.fetch_frame()
if bobframe is not None:
    print("Bob received: {payload_str} (RSSI={rssi} dB, SNR={snr} dB)".format(**{
      **bobframe,
      "payload_str": "".join([chr(b) for b in bobframe['payload']]),
    }))
else:
    print("No frame received")
```

To run one of the example scripts, you can use the `run` task with a python script as parameter:

```bash
./chirpotle.sh run --conf testconf example.py
```

## Getting Started with Jupyter Notebooks

The framework also comes with an integration for Jupyter notebooks.
After creating you configuration like mentioned above, you can just run:

```bash
./chirpotle.sh deploy --conf testconf
./chirpotle.sh restartnodes --conf testconf
./chirpotle.sh notebook --conf testconf
```

On the first run, the `notebook` action will install Jupyter notebook in the virtual environment.
The default notebook folder is called `notebook` and created in the repository root.
It also contains an `examples` folder with notebooks that show you how to setup your experiments and how to integrate the framework with data visualization tools like `matplotlib` to create a seamless workflow.

## System Requirements

Most of the software that is required to run the framework is managed by the framework in the virtual environment.
However, some preparations have to be made to bootstrap the management.

### Controller

For the basic installation of the controller, you need to install Python 3 and the `venv` module.
Everything else will be fetched by the installer and be placed in the virtual environment.

If you do not want to use your system's default python (the installer will check first for `python3`, then for `python` on your path), you can specify the `PYTHON` environment variable during installation to point to a specific executable:

```bash
PYTHON=/opt/my-python/bin/python ./chirpotle.sh install
```

The framework was tested on Debian Buster, but it should work on most other Linux distributions as well.

### Nodes

Calling `./chirpotle.sh deploy` will install the framework globally on the node using an SSH connection as user `root`.
Therefore, the public SSH key of the user running the ChirpOTLE controller must be added to root's `authorized_keys` file on the node.
Furthermore, you need to install Python3 with pip, git, make and gcc on each node.
For Debian-based systems, you can run:

```bash
apt install python3 python3-pip git build-essential
```

You can check if your nodes meet the requirements by calling `./chirpotle.sh deploycheck`.
The output will also suggest quick fixes in case some of the requirements are not met.

Currently supported hardware:

* Raspberry Pi with [Dragino LoRa GPS HAT](https://wiki.dragino.com/index.php?title=Lora/GPS_HAT)
* [Pycom LoPy 4](https://pycom.io/product/lopy4/) with external USB-to-Serial converter ([Documentation](docs/board_lopy4.md))
* [Adafruit Feather M0 LoRa](https://www.adafruit.com/product/3178)

## Development

If you want to modify the framework, you need to install it in development mode for changes to be immediately available.
Therefore, the `install` task supports a `--dev` flag:

```bash
./chirpotle.sh install --dev
```

If you've already installed the framework in the default virtual environment (`env` in the repository root), you can just delete that folder and install again.

## Read Our Paper

The ChirpOTLE framework has been published at [ACM WiSec '20](https://wisec2020.ins.jku.at/) with our paper:

Frank Hessel, Lars Almon, and Flor Álvarez. 2020. ChirpOTLE: A Framework for Practical LoRaWAN Security Evaluation. In _13th ACM Conference on Security and Privacy in Wireless and Mobile Networks (WiSec '20), July 8–10, 2020, Linz (Virtual Event), Austria_. ACM, New York, NY, USA, 11 pages. https://doi.org/10.1145/3395351.3399423

A [preprint](https://arxiv.org/abs/2005.11555) is available.
Scripts and data for all experiments from the paper can be found in [experiments/wisec2020](experiments/wisec2020/README.md).
If you use our work for your research, please cite the paper:

```
@inproceedings{chirpotle2020,
  title     = {ChirpOTLE: A Framework for Practical LoRaWAN Security Evaluation},
  author    = {Hessel, Frank and Almon, Lars and Álvarez, Flor},
  booktitle = {Proceedings of the 13th Conference on Security and Privacy in Wireless and Mobile Networks},
  date      = {2020},
  month     = jul,
  address   = {Linz (Virtual Event), Austria},
  doi       = {10.1145/3395351.3399423},
  publisher = {ACM},
  series    = {WiSec '20},
  url       = {https://doi.org/10.1145/3395351.3399423},
}
```

## License

We provide the ChirpOTLE framework under the [GNU General Public License, Version 3](LICENSE).
However, the repository contains (modified) third-party code and tools which has been published using a different licenses:

| Component                       | License                                                                   | Directory/Files                                              |
| ------------------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------ |
| esp-idf                         | [Apache License, Version 2](submodules/esp-idf/LICENSE)¹                  | `submodules/esp-idf`                                         |
| RIOT                            | [GNU Lesser Public General License, Version 2.1](submodules/RIOT/LICENSE) | `submodules/RIOT`                                            |
| TPy                             | n/a                                                                       | `submodules/tpy`                                             |
| xtensa-esp32-elf for RIOT       | n/a                                                                       | `submodules/xtensa-esp32-elf`                                |
| ubjson (deprecated RIOT module) | [GNU Lesser Public General License, Version 2.1](submodules/RIOT/LICENSE)²| `node/companion-app/riot-modules/{incude/ubjson.h|ubjson/*}` |
| ChirpStack Docker config  | [MIT License](experiments/wisec2020/infrastructure/network/chirpstack/LICENSE)² | `experiments/wisec2020/infrastructure/network/chirpstack`    |
| LoRaMAC node      | [Revised BSD license](experiments/wisec2020/infrastructure/node/LoRaMAC-node/LICENSE)¹² | `experiments/wisec2020/infrastructure/node/LoRaMAC-node/`    |

¹ The submodule may contain submodules on its own, which again is published under different licenses, so please also check the description of the submodule.

² We modified this component and publish the changes under the same license.

## Powered by

[![Logo: TU Darmstadt](assets/logo_tuda.png)](https://www.tu-darmstadt.de)
[![Logo: Secure Mobile Networking Lab](assets/logo_seemoo.png)](https://www.seemoo.de)
[![Logo: CYSEC](assets/logo_cysec.png)](https://www.cysec.de)
[![Logo: ATHENE](assets/logo_athene.png)](https://www.athene-center.de)
[![Logo: emergenCITY](assets/logo_emergencity.png)](https://www.emergencity.de)
