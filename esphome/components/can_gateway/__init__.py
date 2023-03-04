import esphome.config_validation as cv
import esphome.codegen as cg
from esphome.const import CONF_ID
from esphome.components.canbus import CanbusComponent


ns = cg.esphome_ns.namespace('can_gateway')
CanGatewayComponent = ns.class_(
    'CanGatewayComponent',
    cg.Component,
)

CONF_ENTITIES = "entities"

ENTITY_SCHEMA = cv.Schema({
    cv.Required("id"): cv.use_id(cg.EntityBase),
    cv.Required("index"): cv.int_,
    cv.Optional("tpdo"): cv.int_,
})

# STATUS_ENTITY_SCHEMA = cv.Schema({
#     cv.Required("can_id"): cv.int_,
#     cv.Optional("update_interval", default="60s"): cv.positive_time_period_seconds,
# })

CONFIG_SCHEMA = cv.Schema({
    cv.GenerateID(): cv.declare_id(CanGatewayComponent),
    cv.Required("canbus_id"): cv.use_id(CanbusComponent),
    cv.Required("node_id"): cv.int_,
    # cv.Optional("status"): STATUS_ENTITY_SCHEMA,
    cv.Required(CONF_ENTITIES): cv.ensure_list(ENTITY_SCHEMA),
})

def to_code(config):
    can_gateway = cg.new_Pvariable(config[CONF_ID])
    yield cg.register_component(can_gateway, config)
    canbus = yield cg.get_variable(config["canbus_id"])
    node_id = config["node_id"]
    cg.add(can_gateway.initialize(canbus, node_id))
    # status_config = config.get("status", False)
    # if status_config:
    #     cg.add(
    #         can_gateway.add_status(
    #             status_config["can_id"],
    #             status_config["update_interval"].total_seconds
    #         )
    #     )
    entities = sorted(config.get(CONF_ENTITIES, []), key=lambda x: x['index'])
    assert len(entities) == len(set(e['index'] for e in entities)), "All entity indices must be unique!"
    for entity_config in entities:
        entity = yield cg.get_variable(entity_config["id"])
        tpdo = entity_config.get("tpdo", -1)
        cg.add(can_gateway.add_entity(entity, entity_config["index"], tpdo))
