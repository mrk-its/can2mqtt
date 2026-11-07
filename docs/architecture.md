# Architecture

## Startup

`main()` (`src/main.py`) parses the CLI, merges the options with python-can's config
(`can.util.load_config`) and runs `asyncio.run(can2mqtt.start(**config))`. The return value is the
process exit code (`WATCHDOG_TIMEOUT_EXIT_CODE = 42` after a watchdog timeout).

`start()` (`src/can2mqtt/can2mqtt.py`):

1. creates the global `WatchdogTimer`, validates options;
2. connects to MQTT with a last will of `offline` on `<prefix>/can2mqtt/status`, publishes `online`;
3. creates a `canopen.Network` and connects it to the CAN interface with the running event loop, so
   received frames are dispatched on the loop;
4. starts the firmware directory watcher (`--firmware-dir`);
5. runs `can_reader()` and `mqtt_reader()` with `asyncio.gather()` until one of them raises;
6. on exit publishes `offline` availability for every supported node and for can2mqtt.

## Node lifecycle

### Discovery

Nodes are discovered **passively**. canopen's `NodeScanner` sees every received frame and adds the
node id to `can_network.scanner.nodes` for heartbeat (0x700), SDO response (0x580), TPDO
(0x180–0x480) and EMCY (0x80) frames. A node that sends nothing is never found.

### Creation

`can_reader()` loops once per second over `scanner.nodes`. For a node id without a `RemoteNode` it:

- loads `eds/esphome.eds`, adds the TPDO parameter / mapping records (`setup_common_od()`) and calls
  `can_network.add_node()`; this subscribes `0x700 + id` so the node's NMT state follows its heartbeats;
- applies `--sdo-response-timeout` / `--sdo-max-retries`;
- attaches can2mqtt's own attributes to the node object:

  | Attribute | Meaning |
  |---|---|
  | `is_initialized` | registration finished; reset by `reload_node()` |
  | `is_supported` | Identity says ESPHome (`ESPHOME_VENDOR_ID` / `ESPHOME_PRODUCT_CODE`) |
  | `register_task` | running `registration_task()`, or `None` |
  | `reload_count` | bumped by `reload_node()`, lets a registration notice a reboot |
  | `last_heartbeat_time`, `prod_heartbeat_time` | availability computation |
  | `availability`, `availability_topic` | last published availability |
  | `ntm_state_entity`, `update_entity` | built-in entities 0 (NMT state) and 255 (firmware update) |
  | `log_task`, `log_stop` | remote log reader, see `remote_logs.py` |
  | `log_level` | remote log level subscribed to (`remote_logs.setup()`), `None`: no remote logs |
  | `log_level_entity`, `remote_log_level` | the log level select and the level chosen with it, see [Remote log level](#remote-log-level) |
  | `firmware_upload_running` | pauses the remote log reader during OTA |

- adds the heartbeat callback `get_heartbeat_cb()`: updates `last_heartbeat_time`, resets the
  watchdog, publishes the NMT state entity (once registered) and calls `reload_node()` on a boot-up
  heartbeat (status 0).

### Registration

A node is registered once it is `OPERATIONAL`. Its NMT state starts as `INITIALISING` and only changes
on a heartbeat received after `add_node()` (or an NMT command frame seen on COB-ID 0), so registration
starts at the node's next heartbeat.

`can_reader()` doesn't register nodes itself: it starts a `registration_task()` per node, bounded by a
semaphore (`--max-parallel-registrations`), see [parallel-registration.md](parallel-registration.md).
The task calls `register_node()`:

1. reads Identity (vendor id, product code, revision); a node that isn't ESPHome is marked
   `is_initialized` with `is_supported = False` and left alone;
2. `process_node()`:
   - reads SoftwareVersion, DeviceName, HardwareVersion, ProducerHeartbeatTime;
   - publishes discovery config for the NMT state entity (index 0) and the firmware update entity
     (index 255, upload enabled if the node has `Firmware Max Index`) and the NMT buttons (see below);
   - sets up remote logs (`setup_remote_logs()`), publishes the log level select;
   - reads the EntityTypes array (0x2000 for revision 0, 0x2001 for revision 1). For every entity:
     `EntityRegistry.create()`, adds the `states` / `cmds` records at `0x2000 + index * 16 + 1 / + 2`,
     reads the entity metadata from `0x2000 + index * 16`, publishes its discovery config;
   - reads the TPDO configuration (`tpdo.aread()`) while Home Assistant processes the configs;
   - waits for the rest of `HA_DISCOVERY_DELAY` (1s since the last config; states aren't retained, so
     HA must be subscribed to the state topics first), publishes initial states, removes entities the
     node no longer has;
   - attaches `get_tptd_cb()` to the TPDO maps, which turns received PDOs into MQTT state messages;
   - publishes the firmware version available in the firmware directory.

Failures (SDO timeout, unexpected exception) are logged and the node stays uninitialized, so the next
`can_reader()` pass tries again.

### Reload

A boot-up heartbeat calls `reload_node()`: `is_initialized = False`, `reload_count += 1`, the remote log
reader is asked to stop and TPDO maps / callbacks are cleared. The node is registered again when it
reports `OPERATIONAL`.

### Availability

For supported nodes, `publish_node_availability()` computes online = no heartbeat configured, or last
heartbeat within 2 × the producer heartbeat time, and publishes
`<prefix>/can_XXX/availability` when it changes (and right after registration).

### Watchdog

Heartbeat callbacks reset the watchdog. If no heartbeat arrives for `--watchdog-timeout` seconds,
`can_reader()` raises `QuitException` and the process exits with code 42 (to be restarted by the
supervisor / add-on).

## MQTT

`mqtt_reader()` subscribes to `<prefix>/#`:

| Topic | Action |
|---|---|
| `<prefix>/status` = `online` | Home Assistant restarted: republish all discovery configs, states, availability |
| `<prefix>/can_cmd_XXX_KKKKKKKK` | entity command, written to the node with SDO (`CommandMixin`) |
| `<prefix>/node_cmd_XXX/nmt` | NMT command, payload: number (`129`, `0x81`) or name (`RESET`, `pre_operational`, see `canopen.nmt.NMT_COMMANDS`); `XXX` = `000`: all nodes |
| `<prefix>/node_cmd_XXX/update/<flags>` | install firmware from the firmware directory (update entity) |
| `<prefix>/node_cmd_XXX/firmware/<flags>` | upload firmware sent in the payload |
| `<prefix>/node_cmd_XXX/write/<index>[:<subindex>]` | raw SDO writes (hex values) |
| `<prefix>/node_cmd_XXX/log_level` | remote log level (`NONE` … `VERY_VERBOSE`, the log level select) |

Published by can2mqtt:

| Topic | Content |
|---|---|
| `<prefix>/<component>/<unique_id>/config` | Home Assistant discovery config |
| `<prefix>/can_state_XXX_KKKKKKKK` | entity state (from TPDOs) |
| `<prefix>/node_state_XXX/update` | NMT state entity |
| `<prefix>/node_state_XXX/log_level` | remote log level subscribed to |
| `<prefix>/can_XXX/availability` | node availability |
| `<prefix>/can2mqtt/status` | can2mqtt availability (last will `offline`) |

## NMT buttons

Built-in entities (`BUILTIN = True`: NMT state, update, NMT buttons, log level select) are created by can2mqtt for
every node; they aren't in the node's EntityTypes, so the stale entity cleanup in `process_node()`
skips them.

`process_node()` publishes one `NMTButton` (`entities.NMT_BUTTONS`) per command, unique id
`can_XXX_nmt_<key>`, `entity_category: config`, `command_topic` = `<prefix>/node_cmd_XXX/nmt`,
`payload_press` = the command number:

| Button | Command | Enabled by default |
|---|---|---|
| Restart (`device_class: restart`) | `0x81` reset node | yes |
| NMT Start | `0x01` | no |
| NMT Stop | `0x02` | no |
| NMT Pre-operational | `0x80` | no |

esphome-canopen handles reset node with `App.safe_reboot()` (the same as ESPHome's `restart`
button); reset communication (`0x82`) isn't implemented there, so there is no button for it.

`send_nmt_command()` uses `node.nmt.send_command()` for a known node, which also sets the tracked
NMT state (`INITIALISING` after a reset) until the next heartbeat. After a restart the node sends a
boot-up heartbeat: `reload_node()`, and the node is registered again once it is `OPERATIONAL`. An NMT
command during a firmware upload is sent anyway (a restart aborts the upload), with a warning.

## Remote log level

Nodes whose OD has `0x3100` (esphome-canopen `remote_logs:`) get a `RemoteLogLevelSelect`, unique id
`can_XXX_remote_log_level`, options `NONE` … `VERY_VERBOSE` (`remote_logs.ESPHOME_LOG_LEVELS`), state = the
level subscribed to (`node.log_level`). A node flashed without `remote_logs:` loses it at its next
registration.

- Registration subscribes at `node.remote_log_level` (set by the select) or else `--remote-log-level`
  (default `NONE`: not subscribed; `AUTO`: the node's default level `0x3100:5`). With `NONE` nothing is
  written: the node switches its logging off after its Log Timeout.
- A command on `node_cmd_XXX/log_level` sets `node.remote_log_level` and runs `change_remote_log_level()`
  as a background task (stopping the reader may wait for its SDO transfer): `remote_logs.setup()` again,
  `NONE` writes Log Level 0 so the node stops buffering at once.
- `node.remote_log_level` lives on the `RemoteNode`, which survives `reload_node()`: after a node reboot
  the registration subscribes right away, and the node keeps the lines buffered since boot (it clears
  its buffer only when the level goes from 0 to non-zero). Boot logs: choose a level, restart the node.
  It is not persisted: a can2mqtt restart starts from `--remote-log-level` again.
- `remote_logs.setup()` holds a per-node lock (`node.log_setup_lock`): registration and the select
  don't start two readers.

## SDO concurrency rules

- canopen-asyncio's `aupload()` / `adownload()` take `node.sdo.lock` (one SDO transfer per node at a
  time) and run the blocking transfer in a worker thread (`asyncio.to_thread`). Transfers to different
  nodes run concurrently: each node has its own lock and COB-IDs.
- **Never cancel a task that is inside an SDO transfer.** Cancelling releases `node.sdo.lock` while the
  worker thread keeps using the SDO channel; the next request then shares the response queue with it.
  Use a flag the task checks between transfers instead (`remote_logs.stop()`, `reload_count`).
- Worker threads come from the default executor, shared by registrations and remote log readers.
