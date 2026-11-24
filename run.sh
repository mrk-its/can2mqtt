#!/usr/bin/with-contenv bashio
INTERFACE=$(bashio::config 'interface')
CHANNEL=$(bashio::config 'channel')
BITRATE=$(bashio::config 'bitrate')
SERVER=$(bashio::config 'mqtt_server')
TOPIC=$(bashio::config 'mqtt_topic_prefix')
TOPIC=$(test -n "$TOPIC" && echo "-t $TOPIC")
TIMEOUT=$(bashio::config 'sdo_response_timeout' 2.0)
FIRMWARE_DIR=$(bashio::config 'firmware_dir')
REMOTE_LOG_LEVEL=$(bashio::config 'remote_log_level' NONE)
EXTRA_ARGS=$(bashio::config 'extra_args')
if test "$EXTRA_ARGS" == null; then
  EXTRA_ARGS=''
fi

# the command line without the MQTT password (mqtt://user:password@host)
SERVER_LOG=$(printf '%s' "$SERVER" | sed -E 's#^(mqtt://[^:@/]*:).*@#\1***@#')
echo "+ can2mqtt -i $INTERFACE -s $SERVER_LOG -c $CHANNEL -b $BITRATE $TOPIC --sdo-response-timeout $TIMEOUT --firmware-dir $FIRMWARE_DIR --remote-log-level $REMOTE_LOG_LEVEL $EXTRA_ARGS"
can2mqtt -i "$INTERFACE" -s "$SERVER" -c "$CHANNEL" -b "$BITRATE" $TOPIC --sdo-response-timeout $TIMEOUT --firmware-dir $FIRMWARE_DIR --remote-log-level $REMOTE_LOG_LEVEL $EXTRA_ARGS
