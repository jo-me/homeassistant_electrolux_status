import math

from homeassistant.components.sensor import ENTITY_ID_FORMAT
from homeassistant.const import EntityCategory
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from pyelectroluxocp.apiModels import ApplienceStatusResponse
from typing import cast

# from .api import Appliance, ElectroluxLibraryEntity

from .const import DOMAIN
import logging

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Setup binary sensor platform."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    appliances = coordinator.data.get('appliances', None)
    if appliances is not None:
        for appliance_id, appliance in appliances.appliances.items():
            entities = [entity for entity in appliance.entities if entity.entity_type == "entity"]
            _LOGGER.debug("Electrolux add %d entities to registry for appliance %s", len(entities), appliance_id)
            async_add_entities(entities)


def time_seconds_to_minutes(seconds):
    if seconds is not None:
        if seconds == -1:
            return -1
        return int(math.ceil((int(seconds) / 60)))
    return None


class ElectroluxEntity(CoordinatorEntity):
    appliance_status: ApplienceStatusResponse

    def __init__(self, coordinator: any, name: str, config_entry,
                 pnc_id: str, entity_type: str, entity_attr, entity_source, capability: dict[str, any],
                 unit: str, device_class: str, entity_category: EntityCategory):
        super().__init__(coordinator)
        self.root_attribute = "reported"
        self.data = None
        self.coordinator = coordinator
        self._name = name
        self.api = coordinator.api
        self.entity_attr = entity_attr
        self.entity_type = entity_type
        self.entity_source = entity_source
        self.config_entry = config_entry
        self.pnc_id = pnc_id
        self.unit = unit
        self._device_class = device_class
        self._entity_category = entity_category
        _LOGGER.debug("Electrolux new entity %s for appliance %s", name, pnc_id)
        self.entity_id = ENTITY_ID_FORMAT.format(
            f"{self.get_appliance.brand}_{self.get_appliance.name}_{self.entity_source}_{self.entity_attr}")
        self.capability = capability

    @property
    def available(self) -> bool:
        appliance = self.get_appliance()
        if appliance and appliance.connection_state:
            return True
        else:
            return False

    @property
    def state(self) -> StateType:
        appliance = self.get_appliance()
        if appliance:
            return appliance.connection_state
        return None

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    # @property
    # def get_entity(self) -> ApplianceEntity:
    #     return self.get_appliance.get_entity(self.entity_type, self.entity_attr, self.entity_source, None)

    @property
    def get_appliance(self):
        return self.coordinator.data['appliances'].get_appliance(self.pnc_id)

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{self.config_entry.entry_id}-{self.entity_attr}-{self.entity_source}-{self.pnc_id}"

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self.get_appliance.name)},
            "name": self.get_appliance.name,
            "model": self.get_appliance.model,
            "manufacturer": self.get_appliance.brand,
        }

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {
            "integration": DOMAIN,
        }

    @property
    def entity_category(self) -> EntityCategory | None:
        return self._entity_category

    @property
    def device_class(self):
        """Return the device class of the sensor."""
        return self._device_class

    def extract_value(self):
        """Return the appliance attributes of the entity."""
        if self.appliance_status:
            properties = self.appliance_status.get("properties", None)
            if properties:
                root = cast(any, properties)
                if self.root_attribute:
                    root = root.get(self.root_attribute, None)
                if root:
                    if self.entity_source:
                        category: dict[str, any] | None = root.get(self.entity_source, None)
                        if category:
                            return category.get(self.entity_attr)
                    else:
                        return root.get(self.entity_attr, None)
        return None

    def setup(self, data):
        self.data = data

    def update(self, appliance_status: ApplienceStatusResponse):
        self.appliance_status = appliance_status
