#!/bin/bash
NODE_HOSTNAME="$1"

REPODIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )/.."

function print_log {
  printf "\e[7m$NODE_HOSTNAME\e[27m $@ \n"
}

print_log "Starting deployment"

# Stop TPy if it's running
print_log "Stopping tpynode..."
ssh "root@$NODE_HOSTNAME" "killall --quiet tpynode || true"
if [[ "$?" != "0" ]]; then
  print_log "Error: Couldn't stop tpynode"
  exit 1
fi

# Delete an recreate /opt/talonpy-lora
print_log "Recreating /opt/chirpotle"
ssh "root@$NODE_HOSTNAME" "if [ -d /opt/chirpotle ]; then rm -rf /opt/chirpotle; fi; mkdir -p /opt/chirpotle/nodeconf; mkdir -p /opt/chirpotle/modules; mkdir -p /opt/chirpotle/firmwares; mkdir -p /opt/chirpotle/tools"
if [[ "$?" != "0" ]]; then print_log "Creating /opt/chirpotle failed"; exit 1; fi

scp "$CONFDIR/nodeconf"/* "root@$NODE_HOSTNAME:/opt/chirpotle/nodeconf/"
if [[ "$?" != "0" ]]; then print_log "Copying node configurations failed"; exit 1; fi

scp "$REPODIR/node/remote-modules"/*.{py,md,txt} "root@$NODE_HOSTNAME:/opt/chirpotle/modules/"
if [[ "$?" != "0" ]]; then print_log "Copying custom TPy modules failed"; exit 1; fi

scp "$REPODIR/node/tools"/* "root@$NODE_HOSTNAME:/opt/chirpotle/tools/"
if [[ "$?" != "0" ]]; then print_log "Copying node tools failed"; exit 1; fi

print_log "Installing additional dependencies"
ssh "root@$NODE_HOSTNAME" "pip3 install -r /opt/chirpotle/modules/requirements.txt"
if [[ "$?" != "0" ]]; then print_log "Installing dependencies failed"; exit 1; fi

# RIOT binaries
print_log "Copying firmware"
scp -r "$REPODIR/node/companion-app/riot-apps/chirpotle-companion/dist"/* "root@$NODE_HOSTNAME:/opt/chirpotle/firmwares/"

print_log "Flashing connected MCUs"
# Find the node configuration used for this node
# This lookup will results in problems if multiple nodes are running on the same hostname
NODECONF=$(cat <<EOF | python -
from configparser import ConfigParser
c = ConfigParser()
c.read("$CONFFILE")
conf=[c[s]['conf'] for s in c.sections() if c[s]['host']=='$NODE_HOSTNAME'][0]
print(conf)
EOF
)
if [[ -z "$NODECONF" ]]; then print_log "Could not find node configuration for $NODE_HOSTNAME"; exit 1; fi

# Call /opt/chirpotle/tools/remote-flasher.py with the configuration file
ssh "root@$NODE_HOSTNAME" "/opt/chirpotle/tools/remote-flasher.py" "$NODECONF"
if [[ "$?" != "0" ]]; then print_log "Installing firmware failed"; exit 1; fi
