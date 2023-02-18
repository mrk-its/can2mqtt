const int8_t ENTITY_TYPE_BINARY_SENSOR = 1;
const std::map<std::string, uint8_t> BINARY_SENSOR_DEVICE_CLASS = {
    {"None", 0}, {"battery", 1}, {"battery_charging", 2}, {"carbon_monoxide", 3}, {"cold", 4}, {"connectivity", 5},
    {"door", 6}, {"garage_door", 7}, {"gas", 8}, {"heat", 9}, {"light", 10}, {"lock", 11}, {"moisture", 12}, {"motion", 13},
    {"moving", 14}, {"occupancy", 15}, {"opening", 16}, {"plug", 17}, {"power", 18}, {"presence", 19}, {"problem", 20},
    {"running", 21}, {"safety", 22}, {"smoke", 23}, {"sound", 24}, {"tamper", 25}, {"update", 26},
    {"vibration", 27}, {"window", 28}
};

void can_send_binary_sensor_state(esphome::esp32_can::ESP32Can* can_bus, uint32_t entity_id, bool x) {
    std::vector<uint8_t> data = {x};
    can_bus->send_data(entity_id << 4 | PROPERTY_STATE0, true, data);
};

void can_configure_binary_sensor(
    esphome::esp32_can::ESP32Can* can_bus,
    esphome::binary_sensor::BinarySensor* sensor,
    uint32_t entity_id
) {
    uint8_t device_class = 0;
    auto it = BINARY_SENSOR_DEVICE_CLASS.find(sensor->get_device_class());
    if(it != BINARY_SENSOR_DEVICE_CLASS.end()) {
        device_class = it->second;
    }
    std::vector<uint8_t> data = { ENTITY_TYPE_BINARY_SENSOR, device_class };
    can_bus->send_data((entity_id << 4) | PROPERTY_CONFIG, true, data);
    can_send_string_prop(can_bus, entity_id, PROPERTY_CONFIG_NAME, sensor->get_name());

    if(!initialized_entities.count(sensor->get_object_id())) {
        sensor->add_on_state_callback([can_bus, entity_id](bool value) {
            can_send_binary_sensor_state(can_bus, entity_id, value);
        });
        initialized_entities[sensor->get_object_id()] = true;
    }
    if(sensor->has_state())
        can_send_binary_sensor_state(can_bus, entity_id, sensor->state);
};

