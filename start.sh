#!/bin/bash

# Start aria2c RPC
aria2c --enable-rpc --rpc-listen-all=false --rpc-listen-port=6800 --max-connection-per-server=10 --rpc-max-request-size=1024M --seed-time=0 --min-split-size=10M --follow-torrent=mem --split=10 --daemon=true

# Start qbittorrent-nox in background
qbittorrent-nox -d --confirm-legal-notice

# Wait a moment to ensure background services have started
sleep 2

# Start the python bot
python bot.py
