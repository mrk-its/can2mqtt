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


std::map<std::string, bool> initialized_entities;
std::map<uint32_t, std::function< void(std::vector<uint8_t>&)>> can_cmd_handlers;


void can_cmd_message(uint32_t can_id, bool rtr, std::vector<uint8_t> &data) {
    ESP_LOGD("CAN read", "id: %x rtr: %d, len: %d", can_id, rtr, data.size());
    auto it = can_cmd_handlers.find(can_id);
    if(it != can_cmd_handlers.end()) {
        it->second(data);
    }
}

#pragma pack(push, 1)
struct CoverState {
    float position;
    uint8_t state;
};
#pragma pack(pop)

void can_send_cover_state(esphome::esp32_can::ESP32Can* can_bus, uint32_t entity_id, uint8_t state, float pos) {

    CoverState _state = CoverState {
        pos, state
    };

    std::vector<uint8_t> data((uint8_t *)&_state, (uint8_t *)(&_state + 1));
    can_bus->send_data(entity_id << 4 | PROPERTY_STATE0, true, data);
    // std::vector<uint8_t> pos_data((uint8_t *)&pos, ((uint8_t *)&pos) + sizeof(pos));
    // can_bus->send_data(entity_id << 4 | PROPERTY_STATE1, true, pos_data);
}


void can_send_string_prop(esphome::esp32_can::ESP32Can* can_bus, uint32_t entity_id, uint32_t prop, std::string name) {
    std::vector<uint8_t> data(name.begin(), name.end());
    can_bus->send_data((entity_id << 4) | prop, true, data);
};
