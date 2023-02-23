#include <map>
#include "esphome.h"
#include "can_gateway.h"
using namespace esphome::cover;


namespace esphome {
  
  namespace can_gateway {

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
    const std::map<std::string, uint8_t> BINARY_SENSOR_DEVICE_CLASS = {};
    const std::map<std::string, uint8_t> COVER_DEVICE_CLASS = {
        {"None", 0}, {"awning", 1}, {"blind", 2}, {"curtain", 3}, {"damper", 4}, {"door", 5}, {"garage", 6}, {"gate", 7}, {"shade", 8}, {"shutter", 9}, {"window", 10}
    };

    const std::map<std::string, uint8_t> SWITCH_DEVICE_CLASS = {
        {"None", 0}, {"outlet", 1}, {"switch", 2}
    };

    void CanGatewayComponent::can_send_config(uint32_t entity_id, uint8_t entity_type, std::string device_class, uint8_t state_class, std::map<std::string, uint8_t> const& device_map ) {
        uint8_t device_class_id = 0;
        auto it = device_map.find(device_class);
        if(it != device_map.end()) {
            device_class_id = it->second;
        }
        std::vector<uint8_t> data = { entity_type, device_class_id, state_class };
        canbus->send_data((entity_id << 4) | PROPERTY_CONFIG, true, data);        
    }

    void CanGatewayComponent::can_send_string_prop(uint32_t entity_id, uint32_t prop, std::string value) {
      std::vector<uint8_t> data(value.begin(), value.end());
      canbus->send_data((entity_id << 4) | prop, true, data);
    }

    void CanGatewayComponent::add_entity(sensor::Sensor *sensor, uint32_t entity_id) {
      configure_entity([=]() {
        auto name = sensor->get_name();
        auto unit = sensor->get_unit_of_measurement();

        can_send_config(
          entity_id,
          ENTITY_TYPE_SENSOR,
          sensor->get_device_class(),
          sensor->get_state_class(),
          SENSOR_DEVICE_CLASS
        );
        can_send_string_prop(entity_id, PROPERTY_CONFIG_NAME, name);
        can_send_string_prop(entity_id, PROPERTY_CONFIG_UNIT, unit);

        ESP_LOGI(TAG, "configured sensor, entity_id: %d", entity_id);
      });
      sensor->add_on_state_callback([=](float x) {
        std::vector<uint8_t> data((uint8_t *)&x, ((uint8_t *)&x) + sizeof(x));
        canbus->send_data(entity_id << 4, true, data);
      });
    }

    void CanGatewayComponent::add_entity(binary_sensor::BinarySensor *sensor, uint32_t entity_id) {
      configure_entity([=]() {
        auto name = sensor->get_name();
        can_send_config(
          entity_id,
          ENTITY_TYPE_BINARY_SENSOR,
          sensor->get_device_class(),
          0,
          BINARY_SENSOR_DEVICE_CLASS
        );
        can_send_string_prop(entity_id, PROPERTY_CONFIG_NAME, name);
        ESP_LOGI(TAG, "configured binary sensor, entity_id: %d", entity_id);
      });
      sensor->add_on_state_callback([=](bool x) {
        std::vector<uint8_t> data = {x};
        canbus->send_data(entity_id << 4 | PROPERTY_STATE0, true, data);
      });
    }
    
    void CanGatewayComponent::add_entity(esphome::switch_::Switch* switch_, uint32_t entity_id) {
      configure_entity([=]() {
        auto name = switch_->get_name();
        can_send_config(
          entity_id,
          ENTITY_TYPE_SWITCH,
          switch_->get_device_class(),
          0,
          SWITCH_DEVICE_CLASS
        );
        can_send_string_prop(entity_id, PROPERTY_CONFIG_NAME, name);
        ESP_LOGI(TAG, "configured switch, entity_id: %d", entity_id);
      });

      switch_->add_on_state_callback([=](bool value) {
          std::vector<uint8_t> data = {value};
          canbus->send_data(entity_id << 4 | PROPERTY_STATE0, true, data);
      });

      can_cmd_handlers[(entity_id << 4) | PROPERTY_CMD0] = [switch_](std::vector<uint8_t> &data) {
          if(data.size() && data[0]) {
              switch_->turn_on();
          } else {
              switch_->turn_off();
          }
      };
    }

    void CanGatewayComponent::add_entity(esphome::cover::Cover* cover, uint32_t entity_id) {
      configure_entity([=]() {
        can_send_config(entity_id, ENTITY_TYPE_COVER, cover->get_device_class(), 0, COVER_DEVICE_CLASS);
        can_send_string_prop(entity_id, PROPERTY_CONFIG_NAME, cover->get_name());
      });

      cover->add_on_state_callback([=]() {
          ESP_LOGD(
            TAG,
            "on_state callback, op: %s, pos: %f",
            cover_operation_to_str(cover->current_operation),
            cover->position
          );

          if(cover->current_operation == cover::COVER_OPERATION_OPENING) {
              can_send_cover_state(entity_id, 1, cover->position);
          } else if(cover->current_operation == cover::COVER_OPERATION_CLOSING) {
              can_send_cover_state(entity_id, 3, cover->position);
          } else if(cover->current_operation == cover::COVER_OPERATION_IDLE) {
              if(cover->position == cover::COVER_CLOSED) {
                  can_send_cover_state(entity_id, 2, cover->position);
              } else {
                  can_send_cover_state(entity_id, 0, cover->position);
              }
          }

      });

      can_cmd_handlers[(entity_id << 4) | PROPERTY_CMD0] = [=](std::vector<uint8_t> &data) {
          if(data.size()) {
              uint8_t cmd = data[0];
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
          }
      };

      can_cmd_handlers[(entity_id << 4) | PROPERTY_CMD1] = [=](std::vector<uint8_t> &data) {
          if(data.size()) {
              float position = *(float *)&data[0];
              ESP_LOGD(TAG, "set_position: %f", position);
              auto call = cover->make_call();
              call.set_position(position);
              call.perform();
          }
      };
    }

    void CanGatewayComponent::add_status(uint32_t entity_id, uint32_t update_interval) {
      struct timeval tv_now;
      gettimeofday(&tv_now, NULL);
      tv_now.tv_sec -= (time_t)(esp_random() % update_interval);
      status = Status {
        entity_id: entity_id,
        last_time: tv_now,
        update_interval: update_interval
      };

      configure_entity([=]() {
        uint8_t device_class = 9; // data-size
        std::vector<uint8_t> data = { ENTITY_TYPE_CAN_STATUS, device_class, 0 };
        canbus->send_data((entity_id << 4) | PROPERTY_CONFIG, true, data);
        can_send_string_prop(entity_id, PROPERTY_CONFIG_NAME, App.get_name());
      });

    }

    void CanGatewayComponent::on_frame(uint32_t can_id, bool rtr, std::vector<uint8_t> &data) {
        // ESP_LOGV(TAG, "id: %x rtr: %d, len: %d", can_id, rtr, data.size());
        auto it = can_cmd_handlers.find(can_id);
        if(it != can_cmd_handlers.end()) {
            it->second(data);
        }
    }

    void CanGatewayComponent::loop() {
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