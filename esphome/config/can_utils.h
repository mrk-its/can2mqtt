const int8_t ENTITY_TYPE_SENSOR = 0;
const int8_t ENTITY_TYPE_BINARY_SENSOR = 1;
const int8_t ENTITY_TYPE_SWITCH = 2;
const int8_t ENTITY_TYPE_COVER = 3;

const int32_t PROPERTY_STATE0 = 0;
const int32_t PROPERTY_STATE1= 1;
const int32_t PROPERTY_STATE2 = 2;
const int32_t PROPERTY_STATE3 = 3;

const int32_t PROPERTY_CMD0 = 4;
const int32_t PROPERTY_CMD1 = 5;
const int32_t PROPERTY_CMD2 = 6;
const int32_t PROPERTY_CMD3 = 7;


const int32_t PROPERTY_CONFIG = 8;  // D0 - entity type, D1: device_class, D2: state_class

const int32_t PROPERTY_CONFIG_NAME = 9;
const int32_t PROPERTY_CONFIG_NAME2 = 10;
const int32_t PROPERTY_CONFIG_UNIT = 11;


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

const std::map<std::string, uint8_t> BINARY_SENSOR_DEVICE_CLASS = {
    {"None", 0}, {"battery", 1}, {"battery_charging", 2}, {"carbon_monoxide", 3}, {"cold", 4}, {"connectivity", 5},
    {"door", 6}, {"garage_door", 7}, {"gas", 8}, {"heat", 9}, {"light", 10}, {"lock", 11}, {"moisture", 12}, {"motion", 13},
    {"moving", 14}, {"occupancy", 15}, {"opening", 16}, {"plug", 17}, {"power", 18}, {"presence", 19}, {"problem", 20},
    {"running", 21}, {"safety", 22}, {"smoke", 23}, {"sound", 24}, {"tamper", 25}, {"update", 26},
    {"vibration", 27}, {"window", 28}
};

const std::map<std::string, uint8_t> SWITCH_DEVICE_CLASS = {
    {"None", 0}, {"outlet", 1}, {"switch", 2}
};

const std::map<std::string, uint8_t> COVER_DEVICE_CLASS = {
    {"None", 0}, {"awning", 1}, {"blind", 2}, {"curtain", 3}, {"damper", 4}, {"door", 5}, {"garage", 6}, {"gate", 7}, {"shade", 8}, {"shutter", 9}, {"window", 10}
};

std::map<std::string, bool> initialized_entities;
std::map<uint32_t, std::function< void(std::vector<uint8_t>&)>> can_cmd_handlers;


void can_cmd_message(uint32_t can_id, bool rtr, std::vector<uint8_t> &data) {
    ESP_LOGD("CAN read", "id: %x rtr: %d, len: %d", can_id, rtr, data.size());
    auto it = can_cmd_handlers.find(can_id);
    if(it != can_cmd_handlers.end()) {
        it->second(data);
    }
}

void can_send_sensor_state(esphome::esp32_can::ESP32Can* can_bus, uint32_t entity_id, float x) {
    std::vector<uint8_t> data((uint8_t *)&x, ((uint8_t *)&x) + sizeof(x));
    can_bus->send_data(entity_id << 4, true, data);
};

void can_send_switch_state(esphome::esp32_can::ESP32Can* can_bus, uint32_t entity_id, bool x) {
    std::vector<uint8_t> data = {x};
    can_bus->send_data(entity_id << 4 | PROPERTY_STATE0, true, data);

}

void can_send_binary_sensor_state(esphome::esp32_can::ESP32Can* can_bus, uint32_t entity_id, bool x) {
    std::vector<uint8_t> data = {x};
    can_bus->send_data(entity_id << 4 | PROPERTY_STATE0, true, data);
};

void can_send_string_prop(esphome::esp32_can::ESP32Can* can_bus, uint32_t entity_id, uint32_t prop, std::string name) {
    std::vector<uint8_t> data(name.begin(), name.end());
    can_bus->send_data((entity_id << 4) | prop, true, data);
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


void can_configure_switch(
    esphome::esp32_can::ESP32Can* can_bus,
    esphome::switch_::Switch* switch_,
    uint32_t entity_id
) {
    uint8_t device_class = 0;
    auto it = SWITCH_DEVICE_CLASS.find(switch_->get_device_class());
    if(it != SWITCH_DEVICE_CLASS.end()) {
        device_class = it->second;
    }
    std::vector<uint8_t> data = { ENTITY_TYPE_SWITCH, device_class };
    can_bus->send_data((entity_id << 4) | PROPERTY_CONFIG, true, data);
    can_send_string_prop(can_bus, entity_id, PROPERTY_CONFIG_NAME, switch_->get_name());

    if(!initialized_entities.count(switch_->get_object_id())) {
        switch_->add_on_state_callback([can_bus, entity_id](bool value) {
            can_send_switch_state(can_bus, entity_id, value);
        });

        can_cmd_handlers[(entity_id << 4) | PROPERTY_CMD0] = [switch_](std::vector<uint8_t> &data) {
            if(data.size() && data[0]) {
                switch_->turn_on();
            } else {
                switch_->turn_off();
            }
        };
        initialized_entities[switch_->get_object_id()] = true;
    }
    can_send_switch_state(can_bus, entity_id, switch_->state);

};
