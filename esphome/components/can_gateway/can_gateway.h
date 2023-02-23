#pragma once

#include "esphome/core/component.h"
#include "esphome/components/canbus/canbus.h"
#include <vector>
#include <driver/twai.h>

const int8_t ENTITY_TYPE_SENSOR = 0;
const int8_t ENTITY_TYPE_BINARY_SENSOR = 1;
const int8_t ENTITY_TYPE_SWITCH = 2;
const int8_t ENTITY_TYPE_COVER = 3;
const uint8_t ENTITY_TYPE_CAN_STATUS = 254;

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


static const char *const TAG = "can_gateway";

namespace esphome {

  namespace can_gateway {

    #pragma pack(push, 1)
    struct CoverState {
        float position;
        uint8_t state;
    };
    #pragma pack(pop)

    struct Status {
      uint32_t entity_id;
      struct timeval last_time;
      uint32_t update_interval;
    };

    class CanGatewayComponent : public Component {
      std::vector<std::function< void()>> configure_callbacks;
      std::map<uint32_t, std::function< void(std::vector<uint8_t>&)>> can_cmd_handlers;
      canbus::Canbus *canbus;

      optional<Status> status;

      public:
      
      void set_canbus(canbus::Canbus *canbus) {
        this->canbus = canbus;
      }
      
      float get_setup_priority() {
        return this->canbus->get_setup_priority() - 1.0f;
      }

      void setup() {
        random_uint32();
        for (auto cb : this->configure_callbacks) {
            cb();
        }
      }

      void can_send_config(uint32_t entity_id, uint8_t entity_type, std::string device_class, uint8_t state_class, std::map<std::string, uint8_t> const& device_map );
      void can_send_string_prop(uint32_t entity_id, uint32_t prop, std::string value);
      void configure_entity(std::function< void()> cb) {
        this->configure_callbacks.push_back(cb);
      }

      void add_status(uint32_t entity_id, uint32_t update_interval);
      void add_entity(sensor::Sensor *sensor, uint32_t entity_id);
      void add_entity(binary_sensor::BinarySensor *sensor, uint32_t entity_id);
      void add_entity(esphome::switch_::Switch* switch_, uint32_t entity_id);
      void add_entity(esphome::cover::Cover* cover, uint32_t entity_id);

      void on_frame(uint32_t can_id, bool rtr, std::vector<uint8_t> &data);

      void can_send_cover_state(uint32_t entity_id, uint8_t state, float pos) {
          CoverState _state = CoverState {
              pos, state
          };
          std::vector<uint8_t> data((uint8_t *)&_state, (uint8_t *)(&_state + 1));
          canbus->send_data(entity_id << 4 | PROPERTY_STATE0, true, data);
      }

      void can_send_status_counters(uint32_t entity_id, uint32_t prop, uint32_t cnt1, uint32_t cnt2) {
          std::vector<uint32_t> _data = {cnt1, cnt2};
          std::vector<uint8_t> data((uint8_t *)&_data[0], ((uint8_t *)&_data[0]) + 8);
          canbus->send_data((entity_id << 4) | prop, true, data);
      };      
      void loop() override;
    };
  } // namespace can_gateway
} // namespace esphome


