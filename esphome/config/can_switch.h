const int8_t ENTITY_TYPE_SWITCH = 2;

const std::map<std::string, uint8_t> SWITCH_DEVICE_CLASS = {
    {"None", 0}, {"outlet", 1}, {"switch", 2}
};

void can_send_switch_state(esphome::esp32_can::ESP32Can* can_bus, uint32_t entity_id, bool x) {
    std::vector<uint8_t> data = {x};
    can_bus->send_data(entity_id << 4 | PROPERTY_STATE0, true, data);
}

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

