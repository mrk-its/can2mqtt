#!/usr/bin/with-contenv bashio
INTERFACE=$(bashio::config 'interface')
CHANNEL=$(bashio::config 'channel')
BITRATE=$(bashio::config 'bitrate')
SERVER=$(bashio::config 'mqtt_server')
TOPIC=$(bashio::config 'mqtt_topic_prefix')
TOPIC=$(test -n "$TOPIC" && echo "-t $TOPIC")
TIMEOUT=$(bashio::config 'sdo_response_timeout')
TIMEOUT=$(test -n "$TIMEOUT" -a "$TIMEOUT" != null && echo "--sdo-response-timeout $TIMEOUT")

set -x
/app/venv/bin/can2mqtt -i "$INTERFACE" -s "$SERVER" -c "$CHANNEL" -b "$BITRATE" $TOPIC $TIMEOUT
