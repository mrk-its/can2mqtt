# Parallel node registration

## Problem

After a restart can2mqtt needed ~83s until all 18 nodes of a test installation were registered and
online (add-on log, 2026-10-25):

| Phase | Time |
|---|---|
| process start → first registration (waiting for heartbeats) | 3s |
| registration of 18 nodes, one after another | 78s |

Each registration takes 2–6s: reading entity types and metadata over SDO (0–4s, grows with the
number of entities), then the 1s pause before initial states, initial publish and reading the TPDO
configuration (2–4s together). `can_reader()` awaited every registration in its loop, so the total was
the sum over all nodes, and a node that stopped answering would hold up all others for
`--sdo-response-timeout` (10s in the add-on) per transfer.

The same log showed nodes published **offline** right after registration, some for over a minute:
`last_heartbeat_time` was only updated by the heartbeat callback added *during* registration. A node
registered in 2–3s without a heartbeat in that window looked older than 2 × its heartbeat time, and
availability was checked again only on the next pass of the (80s long) loop.

## Design

### Registration in tasks

`can_reader()` is a supervisor that never waits for a registration:

```python
if not node.is_initialized and node.register_task is None and node.nmt.state == "OPERATIONAL":
    node.register_task = asyncio.create_task(registration_task(..., node, semaphore))
if node.is_supported and node.register_task is None:
    await publish_node_availability(...)
```

`registration_task()` holds the semaphore while it registers the node, publishes availability as soon
as the node is registered and clears `node.register_task` when done. Failures are logged; the node
stays uninitialized and a later pass starts a new task. Availability isn't published by the loop while
a node is being registered.

The semaphore (`asyncio.Semaphore(max_parallel_registrations)`, created in `start()`) limits how many
nodes are registered at the same time. Registrations of different nodes don't interfere on the
CANopen level (separate COB-IDs and SDO locks); the limit keeps the load on the CAN adapter and on the
default thread pool (every SDO transfer runs in `asyncio.to_thread`) bounded.

### Reboot during registration

A boot-up heartbeat during registration must not cancel the task — that would release `node.sdo.lock`
while the SDO worker thread is still running (see
[architecture.md](architecture.md#sdo-concurrency-rules)). Instead `reload_node()` increments
`node.reload_count`; `registration_task()` compares it with the value from before `register_node()`
and, if it changed, sets `is_initialized = False` again, so the node is registered again once it is
`OPERATIONAL`.

### Heartbeat tracking from node creation

The heartbeat callback is added when the `RemoteNode` is created in `can_reader()`, not in
`process_node()`. `last_heartbeat_time` is therefore current when registration finishes, and boot-up
heartbeats trigger `reload_node()` even for nodes that are not registered yet. Side effect: heartbeats
of unregistered nodes reset the watchdog too, which matches its purpose (the CAN bus is alive).

## Configuration

| CLI | Default | Meaning |
|---|---|---|
| `-p`, `--max-parallel-registrations` | 4 | nodes registered at the same time; `1` = old serial behaviour |

In the Home Assistant add-on, set it with the `extra_args` option, e.g. `--max-parallel-registrations 6`.

## Results

Measured on the installation above (add-on 0.2.11-b1, default of 4, 2026-10-26), process start →
last `node XX is online`:

| | Before (serial) | After (4 in parallel) |
|---|---|---|
| total | 83s | **23s** |
| wait for first registration | 3s | 1s |
| registration per node | 2–6s, avg 4.3s | 3–7s, avg 4.6s |
| nodes published offline right after registration | 6 | 0 |

Single registrations get slightly slower with four running at once (more traffic on the bus), but
they overlap. The USB-CAN adapter reports a rising `arb_lost` count during startup (105 → 168):
lost arbitration is normal CAN behaviour under higher load (the frame is retried automatically),
`bus_err` and `tx_failed` stayed constant.

## Tests

`tests/test_registration.py`:

- concurrency is bounded by the semaphore and registrations overlap;
- a reboot during registration leaves the node uninitialized for a new registration;
- an SDO communication error is logged and the node can be registered later;
- heartbeats update `last_heartbeat_time` and the watchdog before registration;
- `can_reader()` on a virtual CAN bus: heartbeats → nodes created → registered → online.

## Limits and follow-ups

- Every startup still reads the full node description over SDO. Caching it, keyed by node id,
  Identity and SoftwareVersion (it contains the build timestamp, so it changes with every rebuild),
  would remove most of that traffic.
- The 1s pause before initial states (`HA_DISCOVERY_DELAY`) now overlaps with reading the TPDO
  configuration (1–2s), so it rarely adds time; not measured yet.
- Nodes that send no heartbeat, PDO or EMCY are not discovered (passive `NodeScanner`).
