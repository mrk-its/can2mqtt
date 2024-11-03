#!/usr/bin/with-contenv bashio
INTERFACE=$(bashio::config 'interface')
CHANNEL=$(bashio::config 'channel')
BITRATE=$(bashio::config 'bitrate')
SERVER=$(bashio::config 'mqtt_server')
TOPIC=$(bashio::config 'mqtt_topic_prefix')
TOPIC=$(test -n "$TOPIC" && echo "-t $TOPIC")
TIMEOUT=$(bashio::config 'sdo_response_timeout' 2.0)
FIRMWARE_DIR=$(bashio::config 'firmware_dir')
EXTRA_ARGS=$(bashio::config 'extra_args')

set -x
can2mqtt -i "$INTERFACE" -s "$SERVER" -c "$CHANNEL" -b "$BITRATE" $TOPIC --sdo-response-timeout $TIMEOUT --firmware-dir $FIRMWARE_DIR $EXTRA_ARGS
