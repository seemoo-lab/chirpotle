#!/bin/bash

REPODIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

function containsElement {
  local e match="$1"
  shift
  for e; do [[ "$e" == "$match" ]] && return 0; done
  return 1
}

function chirpotle_check_requirements {
  # Check for Python 3 and set it to $PYTHON
  if [[ -z "$PYTHON" ]]; then
    PYTHON="$(which python3)"
  fi
  if [[ -z "$PYTHON" ]]; then
    PYTHON="$(which python)"
  fi
  if [[ -z "$PYTHON" ]]; then
    echo "No Python 3 installation was found." >&2
    echo "Make sure to intall Python 3 and make it available on PATH or make the PYTHON environment variable point to the executable." >&2
    echo "Quick fix (Debian): sudo apt install python3 python3-pip python3-venv" >&2
    exit 1
  fi
  if ! ($PYTHON -V 2>&1 | grep "Python 3" > /dev/null); then
    echo "No installation of Python 3 could be found." >&2
    echo "Make sure to intall Python 3 and make it available on PATH." >&2
    echo "Quick fix (Debian): sudo apt install python3 python3-pip python3-venv" >&2
    exit 1
  fi
  check_req_python_module "$PYTHON" pip python3-pip
  check_req_python_module "$PYTHON" venv python3-venv
}

function check_req_python_module {
  # Parameters: python_executable module_name
  PYTHON="$1"
  MODULENAME="$2"
  DEBMODULE="$3"
  if ! ($PYTHON -c "import $MODULENAME" &> /dev/null); then
    echo "Missing Python 3 module \"$MODULENAME\". Please install it and make it available to your python installation." >&2
    echo "Currently using Python from: $PYTHON" >&2
    echo "Use a different python installation by pointing the PYTHON environment variable to the executable." >&2
    echo "Quick fix (Debian): sudo apt install $DEBMODULE" >&2
    exit 1
  fi
}

function chirpotle_check_req_gcc_arm_linux {
  TOOLSDIR="$REPODIR/tools"
  GCCDIR="$TOOLSDIR/gcc-arm-8.3-2019.03-x86_64-arm-linux-gnueabihf"
  if [[ ! -d "$GCCDIR" ]]; then
    # GCC 8.3.0 is the current version on Raspberry Pi OS (buster) (2021-02-27)
    ARM_LINUX_URL=https://developer.arm.com/-/media/Files/downloads/gnu-a/8.3-2019.03/binrel/gcc-arm-8.3-2019.03-x86_64-arm-linux-gnueabihf.tar.xz
    ARM_LINUX_MD5=650dc30f7e937fa12e37ea70ff6e10dd
    DLFILENAME="$TOOLSDIR/gcc-arm-linux-gnueabihf.tar.xz"
    echo "Downloading gcc-arm-linux-gnueabihf from $ARM_LINUX_URL"
    mkdir -p "$TOOLSDIR"
    curl -L -o "$DLFILENAME" "$ARM_LINUX_URL"
    if [[ $? != 0 ]] || [[ ! -f "$DLFILENAME" ]]; then
      echo "Could not download gcc-arm-linux-gnueabihf from $ARM_LINUX_URL"
      exit 1
    fi
    if ! (echo "$ARM_LINUX_MD5" "$DLFILENAME" | md5sum -c); then
      echo "Checksum mismatch for gcc-arm-linux-gnueabihf from $ARM_LINUX_URL"
      exit 1
    fi
    tar -C "$TOOLSDIR" -Jxf "$DLFILENAME"
    if [[ $? != 0 ]] || [[ ! -d "$GCCDIR" ]]; then
      echo "Could not extract gcc-arm-linux-gnueabihf from $ARM_LINUX_URL"
      exit 1
    fi
    rm "$DLFILENAME"
  fi
  export PATH="$GCCDIR/bin:$PATH"
  GCC_VER="$(arm-linux-gnueabihf-gcc -dumpversion)"
  EXPECTED_VER="8.3.0"
  COMPARE_RES="$($REPODIR/scripts/compare-version.py "$GCC_VER" "$EXPECTED_VER")"
  if [[ "$?" != "0" ]]; then
    echo "Could not retrieve the version of your GCC for arm-linux-gnueabihf-gcc"
    echo "  Used executable: $(which arm-linux-gnueabihf-gcc)"
    exit 1
  fi
  if [[ "$COMPARE_RES" != "=" ]]; then
    echo "Your installation of arm-linux-gnueabihf-gcc does not match the expected version."
    echo "(it should be auto-installed in $GCCDIR)"
    echo "  Your version:     $GCC_VER (used: $(which arm-linux-gnueabihf-gcc))"
    echo "  Expected version: $EXPECTED_VER"
    exit 1
  fi
}

function chirpotle_check_req_gcc_arm_none {
  TOOLSDIR="$REPODIR/tools"
  GCCDIR="$TOOLSDIR/gcc-arm-none-eabi-9-2019-q4-major"
  if [[ ! -d "$GCCDIR" ]]; then
    # Download the matching ARM none GCC for the riot docker build file
    # https://github.com/RIOT-OS/riotdocker/
    ARM_NONE_URL=https://developer.arm.com/-/media/Files/downloads/gnu-rm/9-2019q4/gcc-arm-none-eabi-9-2019-q4-major-x86_64-linux.tar.bz2
    ARM_NONE_MD5=fe0029de4f4ec43cf7008944e34ff8cc
    DLFILENAME="$TOOLSDIR/gcc-arm-none-eabi.tar.bz2"
    echo "Downloading gcc-arm-none-eabi from $ARM_NONE_URL"
    mkdir -p "$TOOLSDIR"
    curl -L -o "$DLFILENAME" "$ARM_NONE_URL"
    if [[ $? != 0 ]] || [[ ! -f "$DLFILENAME" ]]; then
      echo "Could not download gcc-arm-none-eabi from $ARM_NONE_URL"
      exit 1
    fi
    if ! (echo "$ARM_NONE_MD5" "$DLFILENAME" | md5sum -c); then
      echo "Checksum mismatch for gcc-arm-none-eabi from $ARM_NONE_URL"
      exit 1
    fi
    tar -C "$TOOLSDIR" -jxf "$DLFILENAME"
    if [[ $? != 0 ]] || [[ ! -d "$GCCDIR" ]]; then
      echo "Could not extract gcc-arm-none-eabi from $ARM_NONE_URL"
      exit 1
    fi
    rm "$DLFILENAME"
  fi
  export PATH="$GCCDIR/bin:$PATH"
  GCC_VER="$(arm-none-eabi-gcc -dumpversion)"
  EXPECTED_VER="9.2.1"
  COMPARE_RES="$($REPODIR/scripts/compare-version.py "$GCC_VER" "$EXPECTED_VER")"
  if [[ "$?" != "0" ]]; then
    echo "Could not retrieve the version of your GCC for arm-none-eabi-gcc"
    echo "  Used executable: $(which arm-none-eabi-gcc)"
    exit 1
  fi
  if [[ "$COMPARE_RES" != "=" ]]; then
    echo "Your installation of arm-none-eabi-gcc does not match the expected version."
    echo "(it should be auto-installed in $GCCDIR)"
    echo "  Your version:     $GCC_VER (used: $(which arm-none-eabi-gcc))"
    echo "  Expected version: $EXPECTED_VER"
    exit 1
  fi
}

function chirpotle_check_env {
  if [[ -z "$1" ]]; then
    echo "Name for virtual environment must not be empty." >&2
    echo "Check --envdir / -e argument" >&2
    exit 1
  fi
  if [[ ! -f "$1/bin/activate" ]]; then
    echo "Virtual environment \"$1\" does not exists. You can try to ..." >&2
    echo " ... install ChirpOTLE in the default virtual environment: chirpotle.sh install" >&2
    echo " ... use the --envdir argument to use a custom venv location" >&2
    exit 1
  fi
}

function chirpotle_check_conf {
  if [[ -z "$1" ]]; then
    echo "Configuration directory name must not be empty." >&2
    echo "Check your --confdir / -c argument" >&2
    exit 1
  fi
  if [[ ! -d "$1" ]] || [[ ! -d "$1/hostconf" ]] || [[ ! -d "$1/nodeconf" ]]; then
    echo "The configuration directory does not exists or has an invalid structure. You can try to ..." >&2
    echo " ... install ChirpOTLE with the default configurations: chirpotle.sh install" >&2
    echo " ... check the path again:" >&2
    echo "     $1" >&2
    echo " ... specify a different path using the --confdir argument" >&2
    exit 1
  fi
}

function chirpotle_check_hostconf {
  ABSPATH="$CONFDIR/hostconf/$1.conf"
  if [[ -z "$1" ]]; then echo "Configuration must not be empty." >&2; exit 1; fi
  if [[ ! -e "$ABSPATH" ]]; then
    echo "Configuration $1 does not exist." >&2
    echo "Use \"chirpotle.sh confeditor\" to check for available configurations." >&2
    exit 1
  fi
  echo "$ABSPATH"
}

function chirpotle_confdump {
  # Enter virtual environment
  source "$ENVDIR/bin/activate"

  if [[ "$1" == "--help" || "$1" == "-h" ]]; then
    echo "  Usage: chirpotle.sh confdump [confname]"
    echo ""
    echo "  Dump all (or a specific configuration) to stdout."
    echo ""
    echo "  confname"
    echo "    Optional: Configration to dump. If not present, all"
    echo "    configurations will be shown."
    exit 0
  fi

  # Launch editor
  "$REPODIR/scripts/conf-dump.py" "$CONFDIR" "$1"
} # end of chirpotle_confdump

function chirpotle_confeditor {
  # Enter virtual environment
  source "$ENVDIR/bin/activate"

  # Launch editor
  "$REPODIR/scripts/conf-editor.py" "$CONFDIR"
} # end of chirpotle_confeditor

function chirpotle_deploy {
  # Default parameters
  CONFIGNAME="default"
  INCLUDE_LOCALHOST=0
  BUILD_ALL=0
  export FIRMWARE_ONLY=0

  # Parameter parsing
  while [[ $# -gt 0 ]]
  do
    KEY="$1"
    case "$KEY" in
        -b|--build-all)
          BUILD_ALL=1
          shift
          shift
        ;;
        -c|--conf)
          CONFIGNAME="$2"
          shift
          shift
        ;;
        -h|--help)
          echo "  Usage: chirpotle.sh deploy [--build-all] [--conf <config name>] [--firmware-only] [--help] [--include-localhost]"
          echo ""
          echo "  Setup a virtual environment and install ChirpOTLE and its dependencies."
          echo "  Use the global --env command to specify a custom location for the"
          echo ""
          echo "  IMPORTANT NOTE: The tool will install ChirpOTLE node using root in the"
          echo "    /opt folder of all target hosts and use pip to install Python modules"
          echo "    globally. Make sure that your SSH key is deployed on all nodes as"
          echo "    authorized_key for user root and global installation suits your setup."
          echo ""
          echo "  -b, --build-all"
          echo "    Normally, only firmwares which area required for the given"
          echo "    will be built. Passing this flag builds all firmwares."
          echo "  -c, --conf"
          echo "    The configuration that will be deployed (defaults to \"default\")"
          echo "    Refers to a filename in the conf/hostconf folder, without the .conf"
          echo "    suffix. Use \"chirpotle.sh confeditor\" to edit configurations."
          echo "  --firmware-only"
          echo "    Only re-flash the firmware (requires a full deploy before)."
          echo "  -h, --help"
          echo "    Show this help and quit."
          echo "  --include-localhost"
          echo "    By default, the deployment process will skip nodes with their host"
          echo "    property set to \"localhost\", \"127.0.0.1\" or \"::1\", to not install"
          echo "    the software globally (assuming you don't want that on yourcontroller)."
          echo "    This option disables this check."
          exit 0
        ;;
        --firmware-only)
          export FIRMWARE_ONLY=1
          shift
        ;;
        --include-localhost)
          INCLUDE_LOCALHOST=1
          shift
        ;;
        *)
          echo "Unexpected argument: $KEY" >&2
          echo "Call chirpotle.sh install --help for usage information." >&2
          exit 1
        ;;
    esac
  done

  # Validate config name
  CONFFILE=$(chirpotle_check_hostconf "$CONFIGNAME") || exit 1

  # Enter virtual environment
  source "$ENVDIR/bin/activate"

  # Process localhost configuration
  export CONFDIR="$CONFDIR"
  export CONFFILE="$CONFFILE" # require original file for the lookup of node configuration files during deployment
  TMPCONFFILE="$CONFFILE"
  if [[ "$INCLUDE_LOCALHOST" == "0" ]]; then
    TMPCONFFILE="/tmp/$CONFIGNAME-$$.tmp"
    "$REPODIR/scripts/exclude-localhost.py" "$CONFFILE" > "$TMPCONFFILE"
  fi

  # Full deploy or only re-flashing the firmware?
  if [[ "$FIRMWARE_ONLY" != "1" ]]; then

    # Check dependencies for firmware build
    # -------------------------------------
    # Find used firmwares and platforms
    USED_FIRMWARES=" $($REPODIR/scripts/list-used-firmwares.py firmwares "$CONFDIR" "$CONFFILE") "
    USED_PLATFORMS=" $($REPODIR/scripts/list-used-firmwares.py platforms "$CONFDIR" "$CONFFILE") "

    # Toolchain for ESP32
    if [[ "$USED_PLATFORMS" =~ " esp32 " ]] || [[ $BUILD_ALL == 1 ]]; then
      export ESP32_SDK_DIR="$REPODIR/submodules/esp-idf"
      export PATH="$REPODIR/submodules/xtensa-esp32-elf/bin:$PATH"
    fi

    # Toolchain for bare-metal ARM
    if [[ "$USED_PLATFORMS" =~ " arm_none " ]] || [[ $BUILD_ALL == 1 ]]; then
      chirpotle_check_req_gcc_arm_none
    fi

    # Toolchain for Linux ARM
    if [[ "$USED_PLATFORMS" =~ " arm_linux " ]] || [[ $BUILD_ALL == 1 ]]; then
      chirpotle_check_req_gcc_arm_linux
    fi

    # Build and Bundle the TPy Node
    # -----------------------------
    make -C "$REPODIR/submodules/tpy/node" sdist
    if [[ "$?" != "0" ]]; then
      echo "Building TPy Node failed." >&2
      exit 1
    fi

    # Build the companion application for various toolchains
    # ------------------------------------------------------
    APPDIR="$REPODIR/node/companion-app/riot-apps/chirpotle-companion"
    mkdir -p "$APPDIR/dist"

    # Build LoPy4 (UART mode)
    if [[ "$USED_FIRMWARES" =~ " lopy4-uart " ]] || [[ $BUILD_ALL == 1 ]]; then
      PRECONF=lopy4-uart make -C "$APPDIR" clean all preflash
      if [[ "$?" != "0" ]]; then
        echo "Building the companion application failed for (LoPy4, uart)." >&2
        exit 1
      fi
      (mkdir -p "$APPDIR/dist/lopy4-uart" && cp "$REPODIR/submodules/RIOT/cpu/esp32/bin/bootloader.bin" \
        "$APPDIR/bin/esp32-wroom-32/partitions.csv" "$APPDIR/bin/esp32-wroom-32"/*.bin "$APPDIR/dist/lopy4-uart/")
      if [[ "$?" != "0" ]]; then
        echo "Creating distribution of companion application failed for (LoPy4, uart)." >&2
        exit 1
      fi
    fi

    # Build Feather M0 (UART mode)
    if [[ "$USED_FIRMWARES" =~ " lora-feather-m0 " ]] || [[ $BUILD_ALL == 1 ]]; then
      PRECONF=lora-feather-m0 make -C "$APPDIR" clean all
      if [[ "$?" != "0" ]]; then
        echo "Building the companion application failed for (Feather M0, uart)." >&2
        exit 1
      fi
      (mkdir -p "$APPDIR/dist/lora-feather-m0" && cp "$APPDIR/bin/lora-feather-m0"/*.bin "$APPDIR/dist/lora-feather-m0/")
      if [[ "$?" != "0" ]]; then
        echo "Creating distribution of companion application failed for (Feather M0, uart)." >&2
        exit 1
      fi
    fi

    # Build native-raspi (SPI mode)
    if [[ "$USED_FIRMWARES" =~ " native-raspi " ]] || [[ $BUILD_ALL == 1 ]]; then
      PRECONF=native-raspi make -C "$APPDIR" clean all
      if [[ "$?" != "0" ]]; then
        echo "Building the companion application failed for (native-raspi, uart)." >&2
        exit 1
      fi
      (mkdir -p "$APPDIR/dist/native-raspi" && cp "$APPDIR/bin/native-raspi"/*.elf "$APPDIR/dist/native-raspi/")
      if [[ "$?" != "0" ]]; then
        echo "Creating distribution of companion application failed for (native-raspi, uart)." >&2
        exit 1
      fi
    fi

    # Deploy
    # ------
    # Plain TPy
    tpy deploy -d "$TMPCONFFILE" -p "$REPODIR/submodules/tpy/node/dist/tpynode-latest.tar.gz"
    if [[ "$?" != "0" ]]; then
      echo "Deploying TPy to the nodes failed. Check the output above." >&2
      if [[ ! -z "$TMPCONFFILE" ]] && [[ -f "$TMPCONFFILE" ]]; then rm "$TMPCONFFILE"; fi
      exit 1
    fi
  fi # !FIRMWARE_ONLY

  # Customize TPy for ChirpOTLE
  tpy script -d "$TMPCONFFILE" -s "$REPODIR/scripts/remote-install.sh"
  if [[ "$?" != "0" ]]; then
    echo "Deploying the ChirpOTLE TPy customization to the nodes failed. Check the output above." >&2
    if [[ ! -z "$TMPCONFFILE" ]] && [[ -f "$TMPCONFFILE" ]]; then rm "$TMPCONFFILE"; fi
    exit 1
  fi

  if [[ ! -z "$TMPCONFFILE" ]] && [[ -f "$TMPCONFFILE" ]]; then rm "$TMPCONFFILE"; fi

  echo "Nodes have been stopped during deployment. Remember calling \"chirpotle.sh restartnodes\" before using the framework."
} # end of chirpotle_deploy

function chirpotle_deploycheck {
  # Default parameters
  CONFIGNAME="default"
  INCLUDE_LOCALHOST=0

  # Parameter parsing
  while [[ $# -gt 0 ]]
  do
    KEY="$1"
    case "$KEY" in
        -c|--conf)
          CONFIGNAME="$2"
          shift
          shift
        ;;
        -h|--help)
          echo "  Usage: chirpotle.sh deploycheck [--conf <config name>] [--help] [--include-localhost]"
          echo ""
          echo "  Checks that the remote nodes fulfill all requirements to run the ChirpOTLE"
          echo "  node, e.g. SSH access and Python installation"
          echo ""
          echo "  IMPORTANT NOTE: The tool will install ChirpOTLE node using root in the"
          echo "    /opt folder of all target hosts and use pip to install Python modules"
          echo "    globally. Make sure that your SSH key is deployed on all nodes as"
          echo "    authorized_key for user root and global installation suits your setup."
          echo ""
          echo "  Optional arguments:"
          echo "  -c, --conf"
          echo "    The configuration that will be used (defaults to \"default\")"
          echo "    Refers to a filename in the conf/hostconf folder, without the .conf"
          echo "    suffix. Use \"chirpotle.sh confeditor\" to edit configurations."
          echo "  -h, --help"
          echo "    Show this help and quit."
          echo "  --include-localhost"
          echo "    By default, the deployment process will skip nodes with their host"
          echo "    property set to \"localhost\", \"127.0.0.1\" or \"::1\", to not install"
          echo "    the software globally (assuming you don't want that on yourcontroller)."
          echo "    This option disables this check."
          exit 0
        ;;
        --include-localhost)
          INCLUDE_LOCALHOST=1
          shift
        ;;
        *)
          echo "Unexpected argument: $KEY" >&2
          echo "Call chirpotle.sh install --help for usage information." >&2
          exit 1
        ;;
    esac
  done

  # Validate config name
  CONFFILE=$(chirpotle_check_hostconf "$CONFIGNAME") || exit 1

  # Create temporary config without the localhosts
  if [[ "$INCLUDE_LOCALHOST" == "0" ]]; then
    TMPCONFFILE="/tmp/$CONFIGNAME-$$.tmp"
    "$REPODIR/scripts/exclude-localhost.py" "$CONFFILE" > "$TMPCONFFILE"
    CONFFILE="$TMPCONFFILE"
  fi

  # Enter virtual environment
  source "$ENVDIR/bin/activate"

  # Run check
  tpy script -d "$CONFFILE" -s "$REPODIR/scripts/remote-checkdep.sh"
  RC=$?
  if [[ ! -z "$TMPCONFFILE" ]] && [[ -f "$TMPCONFFILE" ]]; then rm "$TMPCONFFILE"; fi
  exit $RC
}

function chirpotle_install {
  # Default parameters
  INSTALLMODE=install

  # Parameter parsing
  while [[ $# -gt 0 ]]
  do
    KEY="$1"
    case "$KEY" in
        -d|--dev)
          INSTALLMODE=develop
          shift
        ;;
        -h|--help)
          echo "  Usage: chirpotle.sh install [--dev] [--help]"
          echo ""
          echo "  Setup a virtual environment and install ChirpOTLE and its dependencies."
          echo "  Use the global --env command to specify a custom location for the"
          echo ""
          echo "  Optional arguments:"
          echo "  -d, --dev"
          echo "    Do a development install. This will allow you to edit the libraries"
          echo "    and have the changes immediately available."
          echo "  -h, --help"
          echo "    Show this help and quit."
          exit 0
        ;;
        *)
          echo "Unexpected argument: $KEY" >&2
          echo "Call chirpotle.sh install --help for usage information." >&2
          exit 1
        ;;
    esac
  done

  # Validation
  if [[ -z "$ENVDIR" ]]; then echo "Name for virtual environment must not be empty." >&2; exit 1; fi
  if [[ -e "$ENVDIR" ]]; then echo "Virtual environment \"$ENVDIR\" already exists." >&2; exit 1; fi
  if [[ -z "$CONFDIR" ]]; then echo "Name for the configuration directory must not be empty." >&2; exit 1; fi
  CREATE_CONFDIR=1
  if [[ -e "$CONFDIR" ]]; then
    echo "Configuration directory \"$CONFDIR\" already exists." >&2
    if [[ ! -d "$CONFDIR" ]] || [[ ! -d "$CONFDIR/hostconf" ]] || [[ ! -d "$CONFDIR/nodeconf" ]]; then
      echo "The structure of that directory is invalid. Please specify a non-existing directory or a previously used configuration directory" >&2
      exit 1
    else
      CREATE_CONFDIR=0
      echo "Will not recreate the configuration directory." >&2
    fi
  fi

  # Create the configuration directory from the template
  cp -r "$REPODIR/templates/conf" "$CONFDIR"
  if [[ $? != 0 ]]; then echo "Could not create the configuration directory: $CONFDIR" >&2; exit 1; fi

  # Load TPy if not yet installed
  (cd "$REPODIR" && git submodule update --init submodules/tpy)
  if [[ $? != 0 ]]; then echo "Could not initialize the submodule in submodules/tpy" >&2; exit 1; fi

  # Load RIOT if not yet installed
  (cd "$REPODIR" && git submodule update --init submodules/RIOT)
  if [[ $? != 0 ]]; then echo "Could not initialize the submodule in submodules/RIOT" >&2; exit 1; fi

  # Load ESP IDF if not yet installed
  (cd "$REPODIR" && git submodule update --init submodules/esp-idf && cd "submodules/esp-idf" && git submodule init && git submodule update)
  if [[ $? != 0 ]]; then echo "Could not initialize the submodule in submodules/esp-idf" >&2; exit 1; fi

  # Load xtensa compiler if not yet installed
  (cd "$REPODIR" && git submodule update --init submodules/xtensa-esp32-elf)
  if [[ $? != 0 ]]; then echo "Could not initialize the submodule in submodules/xtensa-esp32-elf" >&2; exit 1; fi

  # Create the virtual environment
  $PYTHON -m venv "$ENVDIR"
  if [[ $? != 0 ]]; then echo "Creating the virtual environment failed." >&2; exit 1; fi

  # Enter the virtual environment. From here on, we use python instead of the global $PYTHON
  source "$ENVDIR/bin/activate"

  # Install additional packages required for this script to work
  pip install setuptools packaging
  if [[ $? != 0 ]]; then echo "Could not install Python modules required for managing the framework. Check the output above." >&2; exit 1; fi

  # Install TPy
  (cd "$REPODIR/submodules/tpy/controller" && python setup.py $INSTALLMODE)
  if [[ $? != 0 ]]; then echo "Installing TPy Controller failed. Check the output above." >&2; exit 1; fi

  # Install TPy Node for localnode
  (cd "$REPODIR/submodules/tpy/node" && python setup.py $INSTALLMODE && pip install -r "$REPODIR/node/remote-modules/requirements.txt")
  if [[ $? != 0 ]]; then echo "Installing TPy Node failed. Check the output above." >&2; exit 1; fi
  
  # Install libraries and controller
  (cd "$REPODIR/controller/chirpotle" && python setup.py $INSTALLMODE)
  if [[ $? != 0 ]]; then echo "Installing requirements failed. Check the output above." >&2; exit 1; fi

  # Other tools required by the controller
  pip install pyserial # Flashing of devices
  if [[ $? != 0 ]]; then echo "Installing requirements failed. Check the output above." >&2; exit 1; fi

} # end of chirpotle_install

function chirpotle_interactive {
  # Default parameters
  CONFIGNAME="default"

  # Parameter parsing
  while [[ $# -gt 0 ]]
  do
    KEY="$1"
    case "$KEY" in
        -c|--conf)
          CONFIGNAME="$2"
          shift
          shift
        ;;
        -h|--help)
          echo "  Usage: chirpotle.sh [...] interactive [--conf <config name>] [--help]"
          echo ""
          echo "  Get an interactive Python REPL with nodes and control objects already set up."
          echo ""
          echo "  Optional arguments:"
          echo "  -c, --conf"
          echo "    The configuration that will be used (defaults to \"default\")"
          echo "    Refers to a filename in the conf/hostconf folder, without the .conf"
          echo "    suffix. Use \"chirpotle.sh confeditor\" to edit configurations."
          echo "  --help"
          echo "    Show this help and quit."
          exit 0
        ;;
        *)
          echo "Unexpected argument: $KEY" >&2
          echo "Call chirpotle.sh install --help for usage information." >&2
          exit 1
        ;;
    esac
  done

  # Validate config name
  export CONFFILE=$(chirpotle_check_hostconf "$CONFIGNAME") || exit 1

  # Enter virtual environment
  source "$ENVDIR/bin/activate"

  # Run the script
  python -i "$REPODIR/scripts/interactive-session.py"

} # end of chirpotle_interactive

function chirpotle_localnode {
  # Default parameters
  NODECONF=""

  while [[ $# -gt 0 ]]
  do
    KEY="$1"
    case "$KEY" in
        -c|--conf)
          CONFIGNAME="$2"
          shift
          shift
        ;;
        -h|--help)
          echo "  Usage: chirpotle.sh [...] chirpotle [--help] <node-profile>"
          echo ""
          echo "  Run a ChirpOTLE node on your controller. This function allows you running a"
          echo "  local node without running the usual deploy process on your local machine, and"
          echo "  without installing all tools globally. Make sure that your configuration still"
          echo "  contains an entry for localhost. The \"deploy\" and \"restartnodes\" task will"
          echo "  ignore entries for localhost, if you do not use the --include-localhost flag."
          echo ""
          echo "  Note: If you're connecting an MCU to your local machine and do not use the"
          echo "  default deployment process, you need to flash the companion application"
          echo "  manually. See node/companion-application/riot-apps/chirpotle-companion for"
          echo "  details."
          echo ""
          echo "  Required arguments:"
          echo "  node-profile"
          echo "    Name of the node profile to use. Edit them using \"chirpotle.sh confeditor\"."
          echo "    Basically refers to a file in your conf/nodeconf folder (without the file"
          echo "    extension)."
          echo ""
          echo "  Optional arguments:"
          echo "  --help"
          echo "    Show this help and quit."
          exit 0
        ;;
        *)
          if [[ -z "$NODECONF" ]]; then
            NODECONF="$KEY"
            shift
          else
            echo "Unexpected argument: $KEY" >&2
            echo "Call chirpotle.sh install --help for usage information." >&2
            exit 1
          fi
        ;;
    esac
  done

  # Validate node configuration
  if [[ -z "$NODECONF" ]]; then echo "No node configuration was specified. See \"chirpotle.sh localnode --help\" for details."; exit 1; fi
  NODECONFFILE="$CONFDIR/nodeconf/$NODECONF.conf"
  if [[ ! -f "$NODECONFFILE" ]]; then echo "Node configuration \"$NODECONF\" does not exist."; exit 1; fi

  # Replace the additional modules dir
  TMPCONFFILE="/tmp/node-$$.conf"
  sed -E "s#^module_path *=.*\$#module_path = $REPODIR/node/remote-modules/#" "$NODECONFFILE" > "$TMPCONFFILE"

  # Enter virtual environment
  source "$ENVDIR/bin/activate"

  # Run the node in foreground
  tpynode run -c "$TMPCONFFILE"

  if [[ ! -z "$TMPCONFFILE" ]] && [[ -f "$TMPCONFFILE" ]]; then rm "$TMPCONFFILE"; fi
} # end of chirpotle_localnode

# Launch a Jupyter Notebook server
function chirpotle_notebook {
  # Default parameters
  CONFIGNAME="default"
  NOTEBOOK="$REPODIR/notebook"

  # Parameter parsing
  while [[ $# -gt 0 ]] && [[ -z "$SCRIPTNAME" ]]; do
    KEY="$1"
    case "$KEY" in
        -c|--conf)
          CONFIGNAME="$2"
          shift
          shift
        ;;
        -h|--help)
          echo "  Usage: chirpotle.sh [...] notebook [--conf <config name>] [--help] [--notebook <notebook dir>]"
          echo ""
          echo "  Open a Jupyter Notebook to use with ChirpOTLE."
          echo ""
          echo "  Optional arguments:"
          echo "  -c, --conf"
          echo "    The configuration that will be used (defaults to \"default\")"
          echo "    Refers to a filename in the conf/hostconf folder, without the .conf"
          echo "    suffix. Use \"chirpotle.sh confeditor\" to edit configurations."
          echo "  -h, --help"
          echo "    Show this help and quit."
          echo "  -n, --notebook <notebook-dir>"
          echo "    Notebook folder. Will be created if it does not exist."
          exit 0
        ;;
        -n|--notebook)
          NOTEBOOK="$2"
          shift
          shift
        ;;
        *)
          echo "Invalid argument: $KEY"
          exit 1
        ;;
    esac
  done

  # Validate config name and get absolute path
  export CONFFILE=$(chirpotle_check_hostconf "$CONFIGNAME") || exit 1

  # Enter virtual environment
  source "$ENVDIR/bin/activate"

  # Check for notebook and install it
  if ! ( python -c "import notebook" 2> /dev/null ); then
    pip install notebook
  fi
  if ! ( python -c "import notebook" 2> /dev/null ); then
    echo "Installing notebook failed." >&2
    exit 1
  fi

  # Create directory if not existing
  if [[ ! -d "$NOTEBOOK" ]]; then
    if [[ -e "$NOTEBOOK" ]]; then
      echo "Path $NOTEBOOK already exists, but is not a directory" >&2
      exit 1
    fi
    mkdir -p "$NOTEBOOK"
    if [[ "$?" != "0" ]]; then
      echo "Could not create $NOTEBOOK" >&2
      exit 1
    fi
    cp -r "$REPODIR/templates/notebook"/* "$NOTEBOOK/"
  fi

  (cd "$REPODIR" && jupyter notebook --notebook-dir="$NOTEBOOK")

} # end of chirpotle_notebook

# Run a script in the virtual environment
function chirpotle_run {
  # Default parameters
  CONFIGNAME="default"
  POSITIONAL=()
  SCRIPTNAME=""

  # Parameter parsing
  while [[ $# -gt 0 ]] && [[ -z "$SCRIPTNAME" ]]; do
    KEY="$1"
    case "$KEY" in
        -c|--conf)
          CONFIGNAME="$2"
          shift
          shift
        ;;
        -h|--help)
          echo "  Usage: chirpotle.sh [...] run [--conf <config name>] [--help] <script.py> [scriptargs...]"
          echo ""
          echo "  Setup the framework and run a script. The devices can be accessed in the"
          echo "  script using the following snippet:"
          echo ""
          echo "      from chirpotle.context import tpy_from_context"
          echo "      tc, devices = tpy_from_context()"
          echo ""
          echo "  The first unknown argument is treated as script name, and all following"
          echo "  arguments are passed to the script."
          echo ""
          echo "  Optional arguments:"
          echo "  -c, --conf"
          echo "    The configuration that will be used (defaults to \"default\")"
          echo "    Refers to a filename in the conf/hostconf folder, without the .conf"
          echo "    suffix. Use \"chirpotle.sh confeditor\" to edit configurations."
          echo "  -h, --help"
          echo "    Show this help and quit."
          exit 0
        ;;
        *)
          # First "unknown" argument is script name ...
          SCRIPTNAME="$KEY"
          shift
        ;;
    esac
  done
  # ... all other arguments (if any) are passed to the script as positional args
  while [[ $# -gt 0 ]]; do
    POSITIONAL+=("$1")
    shift
  done

  # Validate config name and get absolute path
  export CONFFILE=$(chirpotle_check_hostconf "$CONFIGNAME") || exit 1

  # Enter virtual environment
  source "$ENVDIR/bin/activate"

  # Run the script
  python "$SCRIPTNAME" "${POSITIONAL[@]}"

} # end of chirpotle_run

function chirpotle_restartnodes {
  # Default parameters
  CONFIGNAME="default"
  INCLUDE_LOCALHOST=0

  # Parameter parsing
  while [[ $# -gt 0 ]]
  do
    KEY="$1"
    case "$KEY" in
        -c|--conf)
          CONFIGNAME="$2"
          shift
          shift
        ;;
        -h|--help)
          echo "  Usage: chirpotle.sh [...] restartnodes [--conf <config name>] [--help] [--include-localhost]"
          echo ""
          echo "  (Re)start all ChirpOTLE nodes which are configured in a configuration."
          echo ""
          echo "  Optional arguments:"
          echo "  -c, --conf"
          echo "    The configuration that will be used (defaults to \"default\")"
          echo "    Refers to a filename in the conf/hostconf folder, without the .conf"
          echo "    suffix. Use \"chirpotle.sh confeditor\" to edit configurations."
          echo "  -h, --help"
          echo "    Show this help and quit."
          echo "  --include-localhost"
          echo "    By default, the deployment process will skip nodes with their host"
          echo "    property set to \"localhost\", \"127.0.0.1\" or \"::1\", to not install"
          echo "    the software globally (assuming you don't want that on yourcontroller)."
          echo "    This option disables this check."
          exit 0
        ;;
        *)
          echo "Invalid argument: $1"
          exit 1
        ;;
    esac
  done

  # Validate config name and get absolute path
  CONFFILE=$(chirpotle_check_hostconf "$CONFIGNAME") || exit 1

  # Create temporary config without the localhosts
  if [[ "$INCLUDE_LOCALHOST" == "0" ]]; then
    TMPCONFFILE="/tmp/$CONFIGNAME-$$.tmp"
    "$REPODIR/scripts/exclude-localhost.py" "$CONFFILE" > "$TMPCONFFILE"
    CONFFILE="$TMPCONFFILE"
  fi

  # Enter virtual environment
  source "$ENVDIR/bin/activate"

  tpy restart -d "$CONFFILE"
  RC=$?
  if [[ ! -z "$TMPCONFFILE" ]] && [[ -f "$TMPCONFFILE" ]]; then rm "$TMPCONFFILE"; fi
  exit $RC
} # end of chirpotle_restartnodes

function chirpotle_tpy {
  # Enter virtual environment
  source "$ENVDIR/bin/activate"

  tpy "$@"
} # end of chirpotle_tpy


function chirpotle_usage {
  echo "  Usage: chirpotle.sh [--confdir <dir>] [--envdir <dir>] <command> [--help]"
  echo ""
  echo "  Where <command> is one of:"
  echo "    confdump     - Dump all (or one specific) configuration to stdout"
  echo "    confeditor   - Launch interactive configration editor"
  echo "    deploy       - Deploy ChirpOTLE to nodes"
  echo "    deploycheck  - Check requirements on ChirpOTLE nodes"
  echo "    help         - Show this information"
  echo "    install      - Install controller on this host in a virtual environment"
  echo "    interactive  - Run an interactive evaluation session"
  echo "    localnode    - Start a local instance of ChirpOTLE node"
  echo "    notebook     - Start a Jupyter Notebook server"
  echo "    restartnodes - (Re)start the remote ChirpOTLE nodes"
  echo "    run          - Run a script in the virtual environment"
  echo "    tpy          - Run a TPy command directly"
  echo ""
  echo "  Global arguments:"
  echo "  -c, --confdir <dir>"
  echo "    Directory to store configuration files, defaults to chirpotle/conf."
  echo "    Configurations can be managed manually or using the confeditor command."
  echo "  -e, --envdir <dir>"
  echo "    The virtual environment to use, defaults to chirpotle/env."
  echo "    Create and populate it using the install command."
  echo ""
  echo "  Use chirpotle.sh <command> --help to learn about command-specific options."
  exit $RC
}

# Main command selection. Pass global arguments up to the command keyword, then
# continue with the command-specific sub-parser
ENVDIR="$REPODIR/env"
CONFDIR="$REPODIR/conf"
ACTION=
RC=0
PRINTVER=1 # Print version, can be disabled by --noversion
CHECKREQ=1 # Check requirements, can be disabled by --skipcheck
while [[ $# -gt 0 ]] && [[ -z "$ACTION" ]]
do
  case "$1" in
    confdump)
      shift
      ACTION=chirpotle_confdump
    ;;
    confeditor)
      shift
      ACTION=chirpotle_confeditor
    ;;
    deploy)
      shift
      ACTION=chirpotle_deploy
    ;;
    deploycheck)
      shift
      ACTION=chirpotle_deploycheck
    ;;
    install)
      shift
      ACTION=chirpotle_install
    ;;
    interactive)
      shift
      ACTION=chirpotle_interactive
    ;;
    localnode)
      shift
      ACTION=chirpotle_localnode
    ;;
    notebook)
      shift
      ACTION=chirpotle_notebook
    ;;
    restartnodes)
      shift
      ACTION=chirpotle_restartnodes
    ;;
    run)
      shift
      ACTION=chirpotle_run
    ;;
    tpy)
      shift
      ACTION=chirpotle_tpy
    ;;
    --help|help)
      shift
      ACTION=chirpotle_usage
      PRINTVER=1
    ;;
    -c|--confdir)
      CONFDIR="$2"
      shift
      shift
    ;;
    -e|--envdir)
      ENVDIR="$2"
      shift
      shift
    ;;
    --skipcheck)
      CHECKREQ=0
      shift
    ;;
    --noversion)
      PRINTVER=0
      shift
    ;;
    *)
      ACTION=chirpotle_usage
      RC=1
    ;;
  esac
done


# Basic setup. Check if we have the required tools available on PATH, otherwise
# abort and instruct the user to install them using the software manager of the
# host OS
if [[ "$CHECKREQ" == "1" ]]; then
  chirpotle_check_requirements
fi
if [[ "$PRINTVER" == "1" ]]; then
  VERSION=$("$PYTHON" "$REPODIR/controller/chirpotle/setup.py" "--version")
  echo "ChirpOTLE - A LoRaWAN Security Evaluation Framework"
  echo "            Controller Version $VERSION"
  echo ""
fi

# Default to usage info with RC=1
if [[ -z "$ACTION" ]]; then
  ACTION=chirpotle_usage
  RC=1
fi

# Validate the virtual environment
if [[ "$ACTION" != "chirpotle_usage" ]] && [[ "$ACTION" != "chirpotle_install" ]]; then
  chirpotle_check_env "$ENVDIR"
  chirpotle_check_conf "$CONFDIR"
fi

# Run the action with the remaining parameters passed to the sub-parser
$ACTION "$@"
