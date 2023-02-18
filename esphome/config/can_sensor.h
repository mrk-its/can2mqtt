const int8_t ENTITY_TYPE_SENSOR = 0;

const std::map<std::string, uint8_t> SENSOR_DEVICE_CLASS = {
    {"None", 0}, {"apparent_power", 1}, {"aqi", 2}, {"atmospheric_pressure", 3}, {"battery", 4}, {"carbon_dioxide", 5},
    {"carbon_monoxide", 6}, {"current", 7}, {"data_rate", 8}, {"data_size", 9}, {"date", 10}, {"distance", 11},
    {"duration", 12}, {"energy", 13}, {"enum", 14}, {"frequency", 15}, {"gas", 16}, {"humidity", 17}, {"illuminance", 18},
    {"irradiance", 19}, {"moisture", 20}, {"monetary", 21}, {"nitrogen_dioxide", 22}, {"nitrogen_monoxide", 23},
    {"nitrous_oxide", 24}, {"ozone", 25}, {"pm1", 26}, {"pm10", 27}, {"pm25", 28}, {"power_factor", 29}, {"power", 30},
    {"precipitation", 31}, {"precipitation_intensity", 32}, {"pressure", 33}, {"reactive_power", 34}, {"signal_strength", 35},
    {"sound_pressure", 36}, {"speed", 37}, {"sulphur_dioxide", 38}, {"temperature", 39}, {"timestamp", 40},
    {"volatile_organic_compounds", 41}, {"voltage", 42}, {"volume", 43}, {"water", 44}, {"weight", 45}, {"wind_speed", 46}
};

void can_send_sensor_state(esphome::esp32_can::ESP32Can* can_bus, uint32_t entity_id, float x) {
    std::vector<uint8_t> data((uint8_t *)&x, ((uint8_t *)&x) + sizeof(x));
    can_bus->send_data(entity_id << 4, true, data);
};

void can_configure_sensor(
    esphome::esp32_can::ESP32Can* can_bus,
    esphome::sensor::Sensor* sensor,
    uint32_t entity_id
) {
    uint8_t device_class = 0;
    auto it = SENSOR_DEVICE_CLASS.find(sensor->get_device_class());
    if(it != SENSOR_DEVICE_CLASS.end()) {
        device_class = it->second;
    }
    std::vector<uint8_t> data = { ENTITY_TYPE_SENSOR, device_class, sensor->get_state_class(), };
    can_bus->send_data((entity_id << 4) | PROPERTY_CONFIG, true, data);

    can_send_string_prop(can_bus, entity_id, PROPERTY_CONFIG_NAME, sensor->get_name());
    can_send_string_prop(can_bus, entity_id, PROPERTY_CONFIG_UNIT, sensor->get_unit_of_measurement());

    if(!initialized_entities.count(sensor->get_object_id())) {
        sensor->add_on_state_callback([can_bus, entity_id](float value) {
            can_send_sensor_state(can_bus, entity_id, value);
        });
        initialized_entities[sensor->get_object_id()] = true;
    }

    if(sensor->has_state())
        can_send_sensor_state(can_bus, entity_id, sensor->state);
};
