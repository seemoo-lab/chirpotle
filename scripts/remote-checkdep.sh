#!/bin/bash
NODE_HOSTNAME=$1

SSHOPTS=(-o "StrictHostKeyChecking no" -o "PasswordAuthentication no")

function print_success {
  HOST="$1"
  CHECK="$2"
  printf "\e[7m $HOST \e[27m ✔️   Success: $CHECK\n"
}

function print_failure {
  HOST="$1"
  CHECK="$2"
  COMMENT="$3"
  printf "\e[7m $HOST \e[27m ❌   Failed: $CHECK\n  → $COMMENT\n"
}

function print_warn {
  HOST="$1"
  CHECK="$2"
  COMMENT="$3"
  printf "\e[7m $HOST \e[27m ⚠️   Failed: $CHECK\n  → $COMMENT\n"
}

CHECK="Node accessible via SSH as root"
WHOAMI=$(ssh "${SSHOPTS[@]}" root@"$NODE_HOSTNAME" whoami)
if [[ "$?" == "0" ]] && [[ "$WHOAMI" == "root" ]]; then
  print_success "$NODE_HOSTNAME" "$CHECK"
else
  print_failure "$NODE_HOSTNAME" "$CHECK" "Could not connect as root@$NODE_HOSTNAME"
  exit
fi

# This will fail for distributions using "python" for Python 3, but so will the TPy install script
CHECK="Python 3 installed"
PYTHON3VER="$(ssh "${SSHOPTS[@]}" root@"$NODE_HOSTNAME" python3 -V | grep 'Python 3')"
if [[ ! -z "$PYTHON3VER" ]]; then
  print_success "$NODE_HOSTNAME" "$CHECK"
else
  print_failure "$NODE_HOSTNAME" "$CHECK" "Please install Python 3 on the node (Debian: apt install python3)"
fi

CHECK="pip for Python 3 installed"
PYTHON3VER="$(ssh "${SSHOPTS[@]}" root@"$NODE_HOSTNAME" pip3 -V | grep 'python 3')"
if [[ ! -z "$PYTHON3VER" ]]; then
  print_success "$NODE_HOSTNAME" "$CHECK"
else
  print_failure "$NODE_HOSTNAME" "$CHECK" "Please install pip3 on the node (Debian: apt install python3-pip)"
fi

CHECK="git installed"
GITBIN="$(ssh "${SSHOPTS[@]}" root@"$NODE_HOSTNAME" which git)"
if [[ ! -z "$GITBIN" ]]; then
  print_success "$NODE_HOSTNAME" "$CHECK"
else
  print_failure "$NODE_HOSTNAME" "$CHECK" "Please install git on the node (Debian: apt install git)"
fi

CHECK="gcc and make installed"
GCCBIN="$(ssh "${SSHOPTS[@]}" root@"$NODE_HOSTNAME" which gcc)"
MAKEBIN="$(ssh "${SSHOPTS[@]}" root@"$NODE_HOSTNAME" which make)"
if [[ ! -z "$GCCBIN" ]] || [[ ! -z "$MAKEBIN" ]]; then
  print_success "$NODE_HOSTNAME" "$CHECK"
else
  print_failure "$NODE_HOSTNAME" "$CHECK" "Please install gcc and make on the node (Debian: apt install build-essential)"
fi

CHECK="HackRF tools installed"
HACKRF="$(ssh "${SSHOPTS[@]}" root@"$NODE_HOSTNAME" which hackrf_transfer)"
if [[ ! -z "$HACKRF" ]]; then
  print_success "$NODE_HOSTNAME" "$CHECK"
else
  print_warn "$NODE_HOSTNAME" "$CHECK" "HackRF tools are missing. You won't be able to use the HackRF module (Debian: apt install hackrf)"
fi
