#pragma once

#include "esphome.h"
using namespace esphome;

#include "esphome/core/component.h"
#include "esphome/components/canbus/canbus.h"
#include <vector>
#include <driver/twai.h>

#include "node_spec.h"
#include "co_if.h"

const int8_t ENTITY_TYPE_DISABLED = 0;
const int8_t ENTITY_TYPE_SENSOR = 1;
const int8_t ENTITY_TYPE_BINARY_SENSOR = 2;
const int8_t ENTITY_TYPE_SWITCH = 3;
const int8_t ENTITY_TYPE_COVER = 4;
const uint8_t ENTITY_TYPE_CAN_STATUS = 254;

const uint8_t ENTITY_INDEX_TYPE = 1;
const uint8_t ENTITY_INDEX_DEVICE_CLASS = 2;
const uint8_t ENTITY_INDEX_NAME = 3;
const uint8_t ENTITY_INDEX_UNIT = 4;

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
    struct Status {
      uint32_t entity_id;
      struct timeval last_time;
      uint32_t update_interval;
    };

    class CanGatewayComponent : public Component {
      CO_NODE node;
      optional<Status> status;
      bool initialized;

      public:
      std::map<uint32_t, std::function< void(void *, uint32_t)>> can_cmd_handlers;

      canbus::Canbus *canbus;
      optional<CO_IF_FRM> recv_frame;

      void initialize(canbus::Canbus *canbus, uint32_t node_id);

      float get_setup_priority() {
        return this->canbus->get_setup_priority() - 1.0f;
      }

      void setup();

      // void add_status(uint32_t entity_id, uint32_t update_interval);
      #ifdef LOG_SENSOR
      void add_entity(sensor::Sensor *sensor, uint32_t entity_id, int8_t tpdo);
      #endif

      #ifdef LOG_BINARY_SENSOR
      void add_entity(binary_sensor::BinarySensor *sensor, uint32_t entity_id, int8_t tpdo);
      #endif

      #ifdef LOG_SWITCH
      void add_entity(esphome::switch_::Switch* switch_, uint32_t entity_id, int8_t tpdo);
      #endif

      #ifdef LOG_COVER
      void add_entity(esphome::cover::Cover* cover, uint32_t entity_id, int8_t tpdo);
      #endif

      void od_add_metadata(
        uint32_t entity_id,
        uint8_t type,
        const std::string &name,
        const std::string &device_class,
        const std::string &unit,
        uint8_t state_class
      );
      void od_add_state(uint32_t entity_id, uint32_t key, void *state, uint8_t size, int8_t tpdo);
      void od_add_cmd(uint32_t entity_id, uint32_t key, std::function< void(void *, uint32_t)> cb);

      void od_set_state(uint32_t key, void *state, uint8_t size);
      void on_frame(uint32_t can_id, bool rtr, std::vector<uint8_t> &data);

      void can_send_status_counters(uint32_t entity_id, uint32_t prop, uint32_t cnt1, uint32_t cnt2) {
          std::vector<uint32_t> _data = {cnt1, cnt2};
          std::vector<uint8_t> data((uint8_t *)&_data[0], ((uint8_t *)&_data[0]) + 8);
          canbus->send_data((entity_id << 4) | prop, true, data);
      };
      void loop() override;
    };
  } // namespace can_gateway
} // namespace esphome
