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
ssh "root@$NODE_HOSTNAME" "if [ -d /opt/chirpotle ]; then rm -rf /opt/chirpotle; fi; mkdir -p /opt/chirpotle/nodeconf; mkdir -p /opt/chirpotle/modules"
if [[ "$?" != "0" ]]; then print_log "Creating /opt/chirpotle failed"; exit 1; fi

scp "$CONFDIR/nodeconf"/* "root@$NODE_HOSTNAME:/opt/chirpotle/nodeconf/"
if [[ "$?" != "0" ]]; then print_log "Copying node configurations failed"; exit 1; fi

scp "$REPODIR/node/remote-modules"/*.{py,md,txt} "root@$NODE_HOSTNAME:/opt/chirpotle/modules/"
if [[ "$?" != "0" ]]; then print_log "Copying custom TPy modules failed"; exit 1; fi

print_log "Installing additional dependencies"
ssh "root@$NODE_HOSTNAME" "pip3 install -r /opt/chirpotle/modules/requirements.txt"
if [[ "$?" != "0" ]]; then print_log "Installing dependencies failed"; exit 1; fi

# TODO: RIOT binaries
