#!/bin/zsh
set -eu
cd "${0:A:h}/.."
python3 backend/relay.py \
  --data "../private-imports/amazon/personalized" \
  --db "../private-imports/amazon/staged/amazon_history.sqlite" \
  --tv-ip 192.168.1.36
