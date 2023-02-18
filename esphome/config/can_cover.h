const int8_t ENTITY_TYPE_COVER = 3;

const std::map<std::string, uint8_t> COVER_DEVICE_CLASS = {
    {"None", 0}, {"awning", 1}, {"blind", 2}, {"curtain", 3}, {"damper", 4}, {"door", 5}, {"garage", 6}, {"gate", 7}, {"shade", 8}, {"shutter", 9}, {"window", 10}
};

void can_configure_cover(
    esphome::esp32_can::ESP32Can* can_bus,
    esphome::cover::Cover* cover,
    uint32_t entity_id
) {
    uint8_t device_class = 0;
    auto it = COVER_DEVICE_CLASS.find(cover->get_device_class());
    if(it != COVER_DEVICE_CLASS.end()) {
        device_class = it->second;
    }
    std::vector<uint8_t> data = { ENTITY_TYPE_COVER, device_class };
    can_bus->send_data((entity_id << 4) | PROPERTY_CONFIG, true, data);
    can_send_string_prop(can_bus, entity_id, PROPERTY_CONFIG_NAME, cover->get_name());

    if(!initialized_entities.count(cover->get_object_id())) {
        cover->add_on_state_callback([=]() {
            // can_send_switch_state(can_bus, entity_id, value);
            ESP_LOGD("cover", "on_state callback, op: %s, pos: %f", cover_operation_to_str(cover->current_operation), cover->position);

            if(cover->current_operation == COVER_OPERATION_OPENING) {
                can_send_cover_state(can_bus, entity_id, 1, cover->position);
            } else if(cover->current_operation == COVER_OPERATION_CLOSING) {
                can_send_cover_state(can_bus, entity_id, 3, cover->position);
            } else if(cover->current_operation == COVER_OPERATION_IDLE) {
                if(cover->position == COVER_CLOSED) {
                    can_send_cover_state(can_bus, entity_id, 2, cover->position);
                } else {
                    can_send_cover_state(can_bus, entity_id, 0, cover->position);
                }
            }

        });

        can_cmd_handlers[(entity_id << 4) | PROPERTY_CMD0] = [=](std::vector<uint8_t> &data) {
            if(data.size()) {
                uint8_t cmd = data[0];
                ESP_LOGD("cover", "cmd: %d", cmd);
                auto call = cover->make_call();
                if(cmd == 0) {
                    call.set_command_stop();
                    call.perform();
                } else if(cmd == 1) {
                    call.set_command_open();
                    call.perform();
                } else if(cmd == 2) {
                    call.set_command_close();
                    call.perform();
                }
            }
        };

        can_cmd_handlers[(entity_id << 4) | PROPERTY_CMD1] = [=](std::vector<uint8_t> &data) {
            if(data.size()) {
                float position = *(float *)&data[0];
                ESP_LOGD("cover", "set_position: %f", position);
                auto call = cover->make_call();
                call.set_position(position);
                call.perform();
            }
        };


        initialized_entities[cover->get_object_id()] = true;
    }
    can_send_cover_state(can_bus, entity_id, 0, 0.0);
};
