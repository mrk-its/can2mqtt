#include <map>
#include "esphome.h"
#include "can_gateway.h"

namespace esphome {
  can_gateway::CanGatewayComponent *global_can_gateway = 0;

  namespace can_gateway {

    // extern "C" {
    //   void log_printf(char *fmt, ...) {
    //     ESP_LOGD(TAG, fmt);
    //   }

    // }

    uint32_t Cmd8Size (CO_OBJ *obj, CO_NODE *node, uint32_t width) {
      const CO_OBJ_TYPE *uint8 = CO_TUNSIGNED8;
      return uint8->Size(obj, node, width);
    }

    CO_ERR   Cmd8Init (CO_OBJ *obj, CO_NODE *node) {
      return CO_ERR_NONE;
    }

    CO_ERR Cmd8Read(struct CO_OBJ_T *obj, struct CO_NODE_T *node, void *buffer, uint32_t size) {
      ESP_LOGV(TAG, "Cmd8Read: key: %x", obj->Key);
      const CO_OBJ_TYPE *uint8 = CO_TUNSIGNED8;
      return uint8->Read(obj, node, buffer, size);
    }

    CO_ERR Cmd8Write(CO_OBJ *obj, CO_NODE *node, void *buffer, uint32_t size) {
      ESP_LOGI(TAG, "Cmd8Write: key: %x, val: %x, size: %x", obj->Key, *((uint8_t *)buffer), size);

      const CO_OBJ_TYPE *uint8 = CO_TUNSIGNED8;
      CO_ERR result = uint8->Write(obj, node, buffer, size);
      uint32_t index = obj->Key & 0xffffff00;

      auto cmd_handlers = global_can_gateway->can_cmd_handlers;
      auto it = cmd_handlers.find(index);
      if(it != cmd_handlers.end()) {
        it->second(buffer, size);
      }
      return result;
    }

    CO_OBJ_TYPE Cmd8 = {
      Cmd8Size,
      Cmd8Init,
      Cmd8Read,
      Cmd8Write,
    };
    #define CO_TCMD8  ((CO_OBJ_TYPE*)&Cmd8)

    CO_OBJ_STR *od_string(const std::string &str) {
      auto od_str = new CO_OBJ_STR();
      od_str->Offset = 0;
      od_str->Start = (uint8_t *)(new std::string(str))->c_str();
      return od_str;
    }

    void CanGatewayComponent::initialize(canbus::Canbus *canbus, uint32_t node_id) {
      NodeSpec.NodeId = node_id;
      CODictInit(&node.Dict, &node, NodeSpec.Dict, NodeSpec.DictLen);

      Automation<std::vector<uint8_t>, uint32_t, bool> *automation;
      LambdaAction<std::vector<uint8_t>, uint32_t, bool> *lambdaaction;
      canbus::CanbusTrigger *canbus_canbustrigger;

      global_can_gateway = this;
      this->canbus = canbus;

      canbus_canbustrigger = new canbus::CanbusTrigger(canbus, 0, 0, false);
      canbus_canbustrigger->set_component_source("canbus");
      App.register_component(canbus_canbustrigger);
      automation = new Automation<std::vector<uint8_t>, uint32_t, bool>(canbus_canbustrigger);
      auto cb = [=](std::vector<uint8_t> x, uint32_t can_id, bool remote_transmission_request) -> void {
          this->on_frame(can_id, remote_transmission_request, x);
      };
      lambdaaction = new LambdaAction<std::vector<uint8_t>, uint32_t, bool>(cb);
      automation->add_actions({lambdaaction});
    }

    void CanGatewayComponent::on_frame(uint32_t can_id, bool rtr, std::vector<uint8_t> &data) {
        recv_frame = {
          {
            can_id,
            {},
            (uint8_t)data.size()
          }
        };
        memcpy(recv_frame.value().Data, &data[0], data.size());
        CONodeProcess(&node);
    }

    uint32_t get_entity_index(uint32_t entity_id) {
      return 0x2000 + entity_id * 16;
    }

    void CanGatewayComponent::od_add_metadata(
      uint32_t entity_id, uint8_t type, const std::string &name, const std::string &device_class,
      const std::string &unit, const std::string &state_class
    ) {
      uint8_t max_sub=1;
      uint32_t index = get_entity_index(entity_id);
      ODAddUpdate(NodeSpec.Dict, CO_KEY(0x2000, entity_id, CO_OBJ_D___R_), CO_TUNSIGNED8, (CO_DATA)type);
      if(name.size())
        ODAddUpdate(NodeSpec.Dict, CO_KEY(index + 0, 1, CO_OBJ_____R_), CO_TSTRING, (CO_DATA)od_string(name));
      if(device_class.size())
        ODAddUpdate(NodeSpec.Dict, CO_KEY(index + 0, 2, CO_OBJ_____R_), CO_TSTRING, (CO_DATA)od_string(device_class));
      if(unit.size())
        ODAddUpdate(NodeSpec.Dict, CO_KEY(index + 0, 3, CO_OBJ_____R_), CO_TSTRING, (CO_DATA)od_string(unit));
      if(state_class.size())
        ODAddUpdate(NodeSpec.Dict, CO_KEY(index + 0, 4, CO_OBJ_D___R_), CO_TSTRING, (CO_DATA)od_string(state_class));
    }

    void CanGatewayComponent::od_add_state(
      uint32_t entity_id, uint32_t key, void *state, uint8_t size, int8_t tpdo
    ) {
      uint32_t async_pdo_mask = tpdo >=0 ? CO_OBJ___A___ | CO_OBJ____P__ : 0;
      uint32_t index = get_entity_index(entity_id);

      uint8_t max_index = 0;
      auto obj = ODFind(NodeSpec.Dict, CO_DEV(index + 1, 0));
      if(obj) max_index = obj -> Data;
      max_index += 1;

      ODAddUpdate(NodeSpec.Dict, CO_KEY(index + 1, max_index, CO_OBJ_D___R_), CO_TUNSIGNED32, key);

      if(tpdo >= 0) {
        ODAddUpdate(NodeSpec.Dict, CO_KEY(0x1800 + tpdo, 1, CO_OBJ_DN__R_), CO_TUNSIGNED32, CO_COBID_TPDO_DEFAULT(tpdo));
        ODAddUpdate(NodeSpec.Dict, CO_KEY(0x1800 + tpdo, 2, CO_OBJ_D___R_), CO_TUNSIGNED8, (CO_DATA)254);

        uint8_t max_index = 0;
        auto obj = ODFind(NodeSpec.Dict, CO_DEV(0x1a00 + tpdo, 0));
        if(obj) max_index = obj->Data;
        max_index += 1;
        uint32_t bits = size * 8;
        ODAddUpdate(NodeSpec.Dict, CO_KEY(0x1a00 + tpdo, max_index, CO_OBJ_D___R_), CO_TUNSIGNED32, CO_LINK(CO_GET_IDX(key), CO_GET_SUB(key), bits));
        ESP_LOGI(TAG, "tpdo: %d, SubIndex: %d, CO_LINK(%x, %x, %x)", tpdo, max_index, CO_GET_IDX(key), CO_GET_SUB(key), bits);
      }
    }

    void  CanGatewayComponent::od_set_state(uint32_t key, void *state, uint8_t size) {
      auto obj = CODictFind(&node.Dict, key);
      if(!obj) return;
      if(CO_IS_PDOMAP(obj->Key)) {
        if(initialized) {
          // trigger tpdo
          COObjWrValue(obj, &node, state, size);
        } else {
          CODictWrBuffer(&node.Dict, key, (uint8_t *)state, size);
        }
      } else {
        CODictWrBuffer(&node.Dict, key, (uint8_t *)state, size);
        if(initialized) {
          uint32_t value = size == 1 ? *(uint8_t *)state : (size == 2 ? *(uint16_t *)state : *(uint32_t *)state);
          CODictWrLong(&node.Dict, CO_DEV(0x3000, 1), key);
          CODictWrLong(&node.Dict, CO_DEV(0x3000, 2), value);
          COTPdoTrigPdo(node.TPdo, 3);
        }
      }
    }

    void CanGatewayComponent::od_add_cmd(
      uint32_t entity_id, uint32_t key, std::function< void(void *, uint32_t)> cb
    ) {
      uint32_t index = get_entity_index(entity_id);

      uint8_t max_index = 0;
      auto obj = ODFind(NodeSpec.Dict, CO_DEV(index + 2, 0));
      if(obj) max_index = obj -> Data;
      max_index += 1;
      ODAddUpdate(NodeSpec.Dict, CO_KEY(index + 2, max_index, CO_OBJ_D___R_), CO_TUNSIGNED32, key);
      can_cmd_handlers[key] = cb;
    }

    uint32_t allocate_state_entry(uint16_t type_id, void *state, uint8_t size, bool tpdo) {
      uint16_t array_index = type_id + 0x5000;
      uint8_t subidx = 0;
      auto obj = ODFind(NodeSpec.Dict, CO_DEV(array_index, 0));
      if(obj) {
        subidx = obj->Data;
      }
      subidx += 1;
      ODAddUpdate(NodeSpec.Dict, CO_KEY(array_index, 0, CO_OBJ_D___R_), CO_TUNSIGNED8, subidx);
      uint32_t key = CO_DEV(array_index, subidx);

      uint32_t async_pdo_mask = tpdo >=0 ? CO_OBJ___A___ | CO_OBJ____P__ : 0;
      uint32_t default_value = state == 0 ? 0 : (size == 1 ? *(uint8_t *)state : (size == 2 ? *(uint16_t *)state : *(uint32_t *)state));
      const CO_OBJ_TYPE *type = size == 1 ? CO_TUNSIGNED8 : (size == 2 ? CO_TUNSIGNED16 : CO_TUNSIGNED32);
      ODAddUpdate(NodeSpec.Dict, CO_KEY(array_index, subidx, async_pdo_mask | CO_OBJ_D___R_), type, (CO_DATA)default_value);

      ESP_LOGD(TAG, "allocated new state entry for type %d: %08x", type_id, key);
      return key;
    }

    uint32_t allocate_cmd_entry(uint16_t type_id, uint8_t size) {
      uint16_t array_index = type_id + 0x5800;
      uint8_t subidx = 0;
      auto obj = ODFind(NodeSpec.Dict, CO_DEV(array_index, 0));
      if(obj) subidx = obj->Data;
      subidx += 1;
      ODAddUpdate(NodeSpec.Dict, CO_KEY(array_index, 0, CO_OBJ_D___R_), CO_TUNSIGNED8, subidx);
      uint32_t key = CO_DEV(array_index, subidx);

      // TODO: CO_TCMD16 / 32
      const CO_OBJ_TYPE *type = size == 1 ? CO_TCMD8 : (size == 2 ? CO_TCMD8 : CO_TCMD8);
      ODAddUpdate(NodeSpec.Dict, CO_KEY(array_index, subidx, CO_OBJ_D___RW), type, (CO_DATA)0);

      ESP_LOGD(TAG, "allocated new cmd entry for type %d: %08x", type_id, key);
      return key;
    }


    #ifdef LOG_SENSOR
    void CanGatewayComponent::add_entity(sensor::Sensor *sensor, uint32_t entity_id, int8_t tpdo) {
      float state = sensor->get_state();
      auto state_key = allocate_state_entry(8, &state, 4, tpdo); // allocate new float
      od_add_metadata(
        entity_id,
        ENTITY_TYPE_SENSOR,
        sensor->get_name(), sensor->get_device_class(), "",
        esphome::sensor::state_class_to_string(sensor->get_state_class())
      );
      od_add_state(entity_id, state_key, &state, 4, tpdo);
      sensor->add_on_state_callback([=](float value) {
        od_set_state(state_key, &value, 4);
      });
    }
    #endif

    #ifdef LOG_BINARY_SENSOR
    void CanGatewayComponent::add_entity(binary_sensor::BinarySensor *sensor, uint32_t entity_id, int8_t tpdo) {
      auto state_key = allocate_state_entry(1, &sensor->state, 1, tpdo); // allocate new bool
      od_add_metadata(
        entity_id,
        ENTITY_TYPE_BINARY_SENSOR,
        sensor->get_name(), sensor->get_device_class(), "", ""
      );
      od_add_state(entity_id, state_key, &sensor->state, 1, tpdo);
      sensor->add_on_state_callback([=](bool x) {
        od_set_state(state_key, &x, 1);
      });
    }
    #endif

    #ifdef LOG_SWITCH
    void CanGatewayComponent::add_entity(esphome::switch_::Switch* switch_, uint32_t entity_id, int8_t tpdo) {
      auto state = switch_->get_initial_state_with_restore_mode().value_or(false);
      auto state_key = allocate_state_entry(1, &state, 1, tpdo); // allocate new bool
      auto cmd_key = allocate_cmd_entry(1, 1); // allocate new bool with default=0

      od_add_metadata(
        entity_id,
        ENTITY_TYPE_SWITCH,
        switch_->get_name(), switch_->get_device_class(), "", ""
      );
      od_add_state(entity_id, state_key, &state, 1, tpdo);
      switch_->add_on_state_callback([=](bool value) {
        od_set_state(state_key, &value, 1);
      });
      od_add_cmd(entity_id, cmd_key, [=](void *buffer, uint32_t size) {
          ESP_LOGI(TAG, "switching to %d", ((uint8_t *)buffer)[0]);
          if(((uint8_t *)buffer)[0]) {
              switch_->turn_on();
          } else {
              switch_->turn_off();
          }
      });
    }
    #endif

    #ifdef LOG_COVER
    uint8_t get_cover_state(esphome::cover::Cover* cover) {
      switch(cover->current_operation) {
        case esphome::cover::COVER_OPERATION_OPENING: return 1;
        case esphome::cover::COVER_OPERATION_CLOSING: return 3;
        case esphome::cover::COVER_OPERATION_IDLE: return cover->position == esphome::cover::COVER_CLOSED ? 2 : 0;
      };
      return 0;
    }

    void CanGatewayComponent::add_entity(esphome::cover::Cover* cover, uint32_t entity_id, int8_t tpdo) {
      uint8_t state = get_cover_state(cover);
      uint8_t position = uint8_t(cover->position * 255);

      auto state_key = allocate_state_entry(5, &state, 1, tpdo); // allocate new uint8
      auto pos_key = allocate_state_entry(5, &position, 1, tpdo); // allocate new uint8

      auto state_cmd_key = allocate_cmd_entry(5, 1); // allocate new uint8
      auto pos_cmd_key = allocate_cmd_entry(5, 1); // allocate new uint8

      od_add_metadata(
        entity_id,
        ENTITY_TYPE_COVER,
        cover->get_name(), cover->get_device_class(), "", ""
      );
      od_add_state(entity_id, state_key, &state, 1, tpdo);
      od_add_state(entity_id, pos_key, &position, 1, tpdo);
      cover->add_on_state_callback([=]() {
        ESP_LOGD(
          TAG,
          "on_state callback, op: %s, pos: %f",
          cover_operation_to_str(cover->current_operation),
          cover->position
        );
        uint8_t position = uint8_t(cover->position * 255);
        uint8_t state = get_cover_state(cover);
        od_set_state(state_key, &state, 1);
        od_set_state(pos_key, &position, 1);
      });
      od_add_cmd(entity_id, state_cmd_key, [=](void *buffer, uint32_t size) {
        uint8_t cmd = *(uint8_t *)buffer;
        ESP_LOGD(TAG, "cmd: %d", cmd);
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
      });
      od_add_cmd(entity_id, pos_cmd_key, [=](void *buffer, uint32_t size) {
        uint8_t cmd = *(uint8_t *)buffer;
        float position = ((float)cmd) / 255.0;
        ESP_LOGD(TAG, "set_position: %f", position);
        auto call = cover->make_call();
        call.set_position(position);
        call.perform();
      });
    }
    #endif

    // void CanGatewayComponent::add_status(uint32_t entity_id, uint32_t update_interval) {
    //   struct timeval tv_now;
    //   gettimeofday(&tv_now, NULL);
    //   tv_now.tv_sec -= (time_t)(esp_random() % update_interval);
    //   status = Status {
    //     entity_id: entity_id,
    //     last_time: tv_now,
    //     update_interval: update_interval
    //   };

    //   configure_entity([=]() {
    //     uint8_t device_class = 9; // data-size
    //     std::vector<uint8_t> data = { ENTITY_TYPE_CAN_STATUS, device_class, 0 };
    //     canbus->send_data((entity_id << 4) | PROPERTY_CONFIG, true, data);
    //     can_send_string_prop(entity_id, PROPERTY_CONFIG_NAME, App.get_name());
    //   });
    // }

    const char *SensorName = "Sensor1";
    const char *SensorUnit = "deg";

    CO_OBJ_STR ManufacturerDeviceNameObj = {0, (uint8_t *)"ESPHome"};

    void CanGatewayComponent::setup() {
      ODAddUpdate(NodeSpec.Dict, CO_KEY(0x1008, 0, CO_OBJ_____R_), CO_TSTRING,     (CO_DATA)(&ManufacturerDeviceNameObj));

      for(uint8_t i=0; i<4; i++) {
        ODAddUpdate(NodeSpec.Dict, CO_KEY(0x1800 + i, 1, CO_OBJ_DN__R_), CO_TUNSIGNED32, CO_COBID_TPDO_DEFAULT(i));
        ODAddUpdate(NodeSpec.Dict, CO_KEY(0x1800 + i, 2, CO_OBJ_D___R_), CO_TUNSIGNED8, (CO_DATA)254);
      }

      ODAddUpdate(NodeSpec.Dict, CO_KEY(0x1a03, 1, CO_OBJ_D___R_), CO_TUNSIGNED32, CO_LINK(0x3000, 1, 32)); // map 32-bits of 0x3000,1 entry to first part of PDO3
      ODAddUpdate(NodeSpec.Dict, CO_KEY(0x1a03, 2, CO_OBJ_D___R_), CO_TUNSIGNED32, CO_LINK(0x3000, 2, 32)); // map 32-bits of 0x3000,2 entry to second part of PDO3

      ODAddUpdate(NodeSpec.Dict, CO_KEY(0x3000, 1, CO_OBJ_D_____ | CO_OBJ____PR_), CO_TUNSIGNED32, (CO_DATA)0);
      ODAddUpdate(NodeSpec.Dict, CO_KEY(0x3000, 2, CO_OBJ_D_____ | CO_OBJ____PR_), CO_TUNSIGNED32, (CO_DATA)0);

      CONodeInit(&node, &NodeSpec);
      auto err = CONodeGetErr(&node);
      if (err != CO_ERR_NONE) {
        ESP_LOGE(TAG, "canopen init error: %d", err);
      }

      CONodeStart(&node);
      CONmtSetMode(&node.Nmt, CO_OPERATIONAL);
      initialized = true;
      ESP_LOGI(TAG, "canopen initialized");
      CO_OBJ *od=NodeSpec.Dict;
      uint32_t index = 0;
      ESP_LOGI(TAG, "############# Object Dictionary #############");
      while (index < NodeSpec.DictLen && (od->Key != 0)) {
        ESP_LOGI(TAG, "OD Index: %02x Key: %08x Data: %08x Type: %08x", index, od->Key, od->Data, od->Type);
        index++;
        od++;
      }
    }

    void CanGatewayComponent::loop() {
      COTmrService(&node.Tmr);
      COTmrProcess(&node.Tmr);

      if(status.has_value()) {
        struct timeval tv_now;
        gettimeofday(&tv_now, NULL);
        if(abs(tv_now.tv_sec - status.value().last_time.tv_sec) >= status.value().update_interval) {
            twai_status_info_t status_info;
            if(twai_get_status_info(&status_info) == ESP_OK) {
                ESP_LOGI(
                    TAG,
                    "status_info:\n"
                    "  state: %d\n  msgs_to_tx: %d\n  msgs_to_rx: %d\n"
                    "  tx_error_counter: %d\n  rx_error_counter: %d\n"
                    "  tx_failed_count: %d\n  rx_missed_count: %d\n"
                    "  arb_lost_count: %d\n  bus_error_count: %d",
                    status_info.state, status_info.msgs_to_tx, status_info.msgs_to_rx,
                    status_info.tx_error_counter, status_info.rx_error_counter,
                    status_info.tx_failed_count, status_info.rx_missed_count,
                    status_info.arb_lost_count, status_info.bus_error_count
                );
                can_send_status_counters(
                    status.value().entity_id, 0,
                    status_info.tx_error_counter, status_info.rx_error_counter
                );
                can_send_status_counters(
                    status.value().entity_id, 1,
                    status_info.tx_failed_count, status_info.rx_missed_count
                );
                can_send_status_counters(
                    status.value().entity_id, 2,
                    status_info.arb_lost_count, status_info.bus_error_count
                );
            }
            status.value().last_time = tv_now;
        }
      }
    }
  }
}
