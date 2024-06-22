"""API for Electrolux Status."""

import json
import logging
import re
from typing import cast

from pyelectroluxocp.apiModels import ApplianceInfoResponse, ApplienceStatusResponse

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import UnitOfTemperature

from .binary_sensor import ElectroluxBinarySensor
from .button import ElectroluxButtonEntity
from .const import (
    BINARY_SENSOR,
    BUTTON,
    COMMON_ATTRIBUTES,
    NUMBER,
    SELECT,
    SENSOR,
    SWITCH,
    Catalog,
    icon_mapping,
)
from .entity import ElectroluxEntity
from .model import ElectroluxDevice
from .number import ElectroluxNumber
from .select import ElectroluxSelect
from .sensor import ElectroluxSensor
from .switch import ElectroluxSwitch

_LOGGER: logging.Logger = logging.getLogger(__package__)

HEADERS = {"Content-type": "application/json; charset=UTF-8"}


class ElectroluxLibraryEntity:
    """Electrolux Library Entity."""

    def __init__(
        self,
        name,
        status: str,
        state: ApplienceStatusResponse,
        appliance_info: ApplianceInfoResponse,
        capabilities: dict[str, any],
    ) -> None:
        """Initaliaze the entity."""
        self.name = name
        self.status = status
        self.state = state
        self.reported_state = self.state["properties"]["reported"]
        self.appliance_info = appliance_info
        self.capabilities = capabilities

    def get_name(self):
        """Get entity name."""
        return self.name

    def get_value(self, attr_name, source=None):
        """Return value by attribute."""
        if source and source != "":
            container: dict[str, any] | None = self.reported_state.get(source, None)
            entry = None if container is None else container.get(attr_name, None)
        else:
            entry = self.reported_state.get(attr_name, None)
        return entry

    def get_sensor_name(self, attr_name: str, container: str | None = None):
        """Get the name of the sensor."""
        attr_name = attr_name.rpartition("/")[-1] or attr_name
        attr_name = attr_name[0].upper() + attr_name[1:]
        attr_name = attr_name.replace("_", " ")
        group = ""
        words = []
        s = attr_name
        for i in range(len(s)):  # [consider-using-enumerate]
            char = s[i]
            if group == "":
                group = char
            else:
                if char == " " and len(group) > 0:
                    words.append(group)
                    group = ""
                    continue

                if (
                    (char.isupper() or char.isdigit())
                    and (s[i - 1].isupper() or s[i - 1].isdigit())
                    and (
                        (i == len(s) - 1) or (s[i + 1].isupper() or s[i + 1].isdigit())
                    )
                ):
                    group += char
                elif (char.isupper() or char.isdigit()) and s[i - 1].islower():
                    if re.match("^[A-Z0-9]+$", group):
                        words.append(group)
                    else:
                        words.append(group.lower())
                    group = char
                else:
                    group += char
        if len(group) > 0:
            if re.match("^[A-Z0-9]+$", group):
                words.append(group)
            else:
                words.append(group.lower())
        return " ".join(words)

    def get_sensor_name_old(self, attr_name: str, container: str | None = None):
        """Convert sensor format.

        ex: "fCMiscellaneousState/detergentExtradosage" to "Detergent extradosage".
        """
        attr_name = attr_name.rpartition("/")[-1] or attr_name
        attr_name = attr_name[0].upper() + attr_name[1:]
        attr_name = " ".join(re.findall("[A-Z][^A-Z]*", attr_name))
        return attr_name.capitalize()

    def get_category(self, attr_name: str):
        """Extract category.

        ex: "fCMiscellaneousState/detergentExtradosage" to "fCMiscellaneousState".
        or "" if none
        """
        return attr_name.rpartition("/")[0]

    def get_entity_name(self, attr_name: str, container: str | None = None):
        """Convert Entity Name.

        ex: Convert format "fCMiscellaneousState/detergentExtradosage" to "detergentExtradosage"
        """
        return attr_name.rpartition("/")[-1] or attr_name

    def get_entity_unit(self, attr_name: str):
        """Get entity unit type."""
        capability_def: dict[str, any] | None = self.capabilities.get(attr_name, None)
        if not capability_def:
            return None
        # Type : string, int, number, boolean (other values ignored)
        type_units = capability_def.get("type", None)
        if not type_units:
            return None
        if type_units == "temperature":
            return UnitOfTemperature.CELSIUS
        return None

    def get_entity_device_class(self, attr_name: str):
        """Get entity device class."""
        capability_def: dict[str, any] | None = self.capabilities.get(attr_name, None)
        if not capability_def:
            return None
        # Type : string, int, number, boolean (other values ignored)
        type_class = capability_def.get("type", None)
        if not type_class:
            return None
        if type_class == "temperature":
            return SensorDeviceClass.TEMPERATURE
        return None

    def get_entity_type(self, attr_name: str):
        """Get entity type."""
        capability_def: dict[str, any] | None = self.capabilities.get(attr_name, None)
        if not capability_def:
            return None
        # Type : string, int, number, boolean (other values ignored)
        type_object = capability_def.get("type", None)
        if not type_object:
            return None
        # Access : read, readwrite (other values ignored)
        access = capability_def.get("access", None)
        if not access:
            return None

        # Exception (Electrolux bug)
        if (
            type_object == "boolean"
            and access == "readwrite"
            and capability_def.get("values", None) is not None
        ):
            return SWITCH

        # List of values ? if values is defined and has at least 1 entry
        values: dict[str, any] | None = capability_def.get("values", None)
        if (
            values
            and access == "readwrite"
            and isinstance(values, dict)
            and len(values) > 0
        ):
            if type_object != "number" or capability_def.get("min", None) is None:
                return SELECT

        match type_object:
            case "boolean":
                if access == "read":
                    return BINARY_SENSOR
                if access == "readwrite":
                    return SWITCH
            case "temperature":
                if access == "read":
                    return SENSOR
                if access == "readwrite":
                    return NUMBER
            case _:
                if access == "read" and type_object in [
                    "number",
                    "int",
                    "boolean",
                    "string",
                ]:
                    return SENSOR
                if type_object in ("int", "number"):
                    return NUMBER
        return None

    def sources_list(self):
        """List the capability types."""
        if self.capabilities is None:
            return None
        return [
            key
            for key in list(self.capabilities.keys())
            if not key.startswith("applianceCareAndMaintenance")
        ]


class Appliance:
    """Define the Appliance Class."""

    brand: str
    device: str
    entities: list[ElectroluxEntity]
    coordinator: any

    def __init__(
        self,
        coordinator: any,
        name: str,
        pnc_id: str,
        brand: str,
        model: str,
        state: ApplienceStatusResponse,
    ) -> None:
        """Initiate the appliance."""
        self.own_capabilties = False
        self.data = None
        self.coordinator = coordinator
        self.model = model
        self.pnc_id = pnc_id
        self.name = name
        self.brand = brand
        self.state: ApplienceStatusResponse = state

    def update_missing_entities(self):
        """Add missing entities when no capabilities returned by the API, do it dynamically."""
        if not self.own_capabilties:
            return
        properties = self.state.get("properties")
        capability = ""
        if properties:
            reported = properties.get("reported")
            if reported:
                for key, items in Catalog.items():
                    for item in items:
                        category = item.category
                        if (
                            category
                            and reported.get(category, None)
                            and reported.get(category, None).get(key)
                        ) or (not category and reported.get(key, None)):
                            found: bool = False
                            for entity in self.entities:
                                if (
                                    entity.entity_attr == key
                                    and entity.entity_source == category
                                ):
                                    found = True
                                    capability = (
                                        key if category is None else category + "/" + key
                                    )
                                    self.data.capabilities[capability] = item.capability_info
                                    break
                            if not found:
                                _LOGGER.debug(
                                    "Electrolux discovered new entity from extracted data. Category: %s Key: %s",
                                    category,
                                    key,
                                )
                                entity = self.get_entity(capability)
                                if entity:
                                    self.entities.append(entity)

    def get_entity(self, capability: str) -> ElectroluxEntity | None:
        """Return the entity."""
        entity_type = self.data.get_entity_type(capability)
        entity_name = self.data.get_entity_name(capability)
        category = self.data.get_category(capability)
        capability_info: dict[str, any] = self.data.capabilities[capability]
        device_class = self.data.get_entity_device_class(capability)
        entity_category = None
        entity_icon = None
        unit = self.data.get_entity_unit(capability)

        # item : capability, category, DeviceClass, Unit, EntityCategory
        catalog_item = Catalog.get(capability, None)
        if catalog_item:
            if capability_info is None:
                capability_info = catalog_item.capability_info
            device_class = catalog_item.device_class
            unit = catalog_item.unit
            entity_category = catalog_item.entity_category
            entity_icon = catalog_item.entity_icon

        if entity_type == SENSOR:
            return ElectroluxSensor(
                name=f"{self.data.get_name()} {self.data.get_sensor_name(entity_name, capability)}",
                coordinator=self.coordinator,
                config_entry=self.coordinator.config_entry,
                entity_type=entity_type,
                entity_attr=entity_name,
                entity_source=category,
                pnc_id=self.pnc_id,
                capability=capability_info,
                unit=unit,
                entity_category=entity_category,
                device_class=device_class,
                icon=entity_icon,
            )
        if entity_type == BINARY_SENSOR:
            return ElectroluxBinarySensor(
                name=f"{self.data.get_name()} {self.data.get_sensor_name(entity_name, capability)}",
                coordinator=self.coordinator,
                config_entry=self.coordinator.config_entry,
                entity_type=entity_type,
                entity_attr=entity_name,
                entity_source=category,
                pnc_id=self.pnc_id,
                capability=capability_info,
                unit=unit,
                entity_category=entity_category,
                device_class=device_class,
                icon=entity_icon,
            )
        if entity_type == SELECT:
            return ElectroluxSelect(
                name=f"{self.data.get_name()} {self.data.get_sensor_name(entity_name, capability)}",
                coordinator=self.coordinator,
                config_entry=self.coordinator.config_entry,
                entity_type=entity_type,
                entity_attr=entity_name,
                entity_source=category,
                pnc_id=self.pnc_id,
                capability=capability_info,
                unit=unit,
                entity_category=entity_category,
                device_class=device_class,
                icon=entity_icon,
            )
        if entity_type == NUMBER:
            return ElectroluxNumber(
                name=f"{self.data.get_name()} {self.data.get_sensor_name(entity_name, capability)}",
                coordinator=self.coordinator,
                config_entry=self.coordinator.config_entry,
                entity_type=entity_type,
                entity_attr=entity_name,
                entity_source=category,
                pnc_id=self.pnc_id,
                capability=capability_info,
                unit=unit,
                entity_category=entity_category,
                device_class=device_class,
                icon=entity_icon,
            )
        if entity_type == SWITCH:
            return ElectroluxSwitch(
                name=f"{self.data.get_name()} {self.data.get_sensor_name(entity_name, capability)}",
                coordinator=self.coordinator,
                config_entry=self.coordinator.config_entry,
                entity_type=entity_type,
                entity_attr=entity_name,
                entity_source=category,
                pnc_id=self.pnc_id,
                capability=capability_info,
                unit=unit,
                entity_category=entity_category,
                device_class=device_class,
                icon=entity_icon,
            )
        return None

    def setup(self, data: ElectroluxLibraryEntity):
        """Configure the entity."""
        self.data: ElectroluxLibraryEntity = data
        self.entities: list = []
        entities: list = []
        # Extraction of the appliance capabilities & mapping to the known entities of the component
        capabilities_names = self.data.sources_list()  # [ "applianceState", "autoDosing",..., "userSelections/analogTemperature",...]

        # No capabilities returned (unstable API) => rebuild them from catalog + sample data
        if capabilities_names is None and self.state:
            capabilities_names = []
            capabilities = {}
            reported = self.state.get("properties", {}).get("reported")
            if reported:
                for key, item in Catalog.items():
                    category = item.category
                    if (
                        (
                            category
                            and reported.get(category, None)
                            and reported.get(category, None).get(key)
                        )
                        or (not category and reported.get(key, None))
                        or key == "executeCommand"
                    ):
                        path = f"{category}/{key}" if category else key
                        capabilities[path] = item.capability_info
                        capabilities_names.append(path)
                self.data.capabilities = capabilities
                _LOGGER.debug(
                    "Electrolux rebuilt capabilities due to API malfunction: %s",
                    json.dumps(capabilities),
                )
        # Add common entities
        for common_attribute in COMMON_ATTRIBUTES:
            entity_name = data.get_entity_name(common_attribute)
            category = data.get_category(common_attribute)
            found = False
            # Check if not reported in capabilities
            for capability in capabilities_names:
                entity_name2 = data.get_entity_name(capability)
                category2 = data.get_category(capability)
                if entity_name2 == entity_name and (
                    (category is None and category2 is None) or category == category2
                ):
                    found = True
                    break
            if found:
                continue
            catalog_item = Catalog.get(entity_name, None)
            if catalog_item:
                self.data.capabilities[common_attribute] = catalog_item.capability_info
                entity = self.get_entity(common_attribute)
                entities.append(entity)

        # For each capability src
        for capability in capabilities_names:
            capability_info: dict[str, any] = data.capabilities[capability]
            entity_name = data.get_entity_name(capability)
            category = data.get_category(capability)
            device_class = None
            entity_category = None
            # unit = None
            # item : capability, category, DeviceClass, Unit, EntityCategory
            catalog_items = cast(list[ElectroluxDevice], Catalog.get(entity_name, None))

            # Handle the case where the capabilities defined in catalog are richer than provided one from server
            if catalog_item:
                if capability_info is None:
                    capability_info = catalog_item.capability_info
                elif catalog_item.capability_info:
                    for key, item in catalog_item.capability_info.items():
                        if capability_info.get(key, None) is None:
                            capability_info[key] = item
                device_class = catalog_item.device_class

            if capability == "executeCommand":
                commands: dict[str, str] = capability_info["values"]
                commands_keys = list(commands.keys())
                entities.extend(
                    ElectroluxButtonEntity(
                        name=f"{data.get_name()} {data.get_sensor_name(command, capability)}",
                        coordinator=self.coordinator,
                        config_entry=self.coordinator.config_entry,
                        entity_type=BUTTON,
                        entity_attr=entity_name,
                        entity_source=category,
                        pnc_id=self.pnc_id,
                        icon=icon_mapping.get(command, "mdi:gesture-tap-button"),
                        val_to_send=command,
                        capability=capability_info,
                        entity_category=entity_category,
                        device_class=device_class,
                    )
                    for command in commands_keys
                )
                # for command in commands_keys:
                #     entities.append(
                #         ElectroluxButtonEntity(
                #             name=f"{data.get_name()} {data.get_sensor_name(command, capability)}",
                #             coordinator=self.coordinator,
                #             config_entry=self.coordinator.config_entry,
                #             entity_type=BUTTON,
                #             entity_attr=entity_name,
                #             entity_source=category,
                #             pnc_id=self.pnc_id,
                #             icon=icon_mapping.get(command, "mdi:gesture-tap-button"),
                #             val_to_send=command,
                #             capability=capability_info,
                #             entity_category=entity_category,
                #             device_class=device_class,
                #         )
                #     )
                continue

            entity = self.get_entity(capability)
            if entity:
                entities.append(entity)

        # Setup each found entities
        self.entities = entities
        for entity in entities:
            entity.setup(data)

    def update_reported_data(self, reported_data: dict[str, any]):
        """Update the reported data."""
        _LOGGER.debug("Electrolux update reported data %s", reported_data)
        try:
            local_reported_data = self.state.get("properties", None).get(
                "reported", None
            )
            local_reported_data.update(reported_data)
            _LOGGER.debug("Electrolux updated reported data %s", self.state)
            self.update_missing_entities()
            for entity in self.entities:
                entity.update(self.state)

        except Exception as ex:  # noqa: BLE001
            _LOGGER.debug(
                "Electrolux status could not update reported data with %s. %s",
                reported_data,
                ex,
            )

    def update(self, appliance_status: ApplienceStatusResponse):
        """Update appliance status."""
        self.state = appliance_status
        self.update_missing_entities()
        for entity in self.entities:
            entity.update(self.state)


class Appliances:
    """Appliance class definition."""

    def __init__(self, appliances: dict[str, Appliance]) -> None:
        """Initialize the class."""
        self.appliances = appliances

    def get_appliance(self, pnc_id) -> Appliance:
        """Return the appliance."""
        return self.appliances.get(pnc_id, None)

    def get_appliances(self) -> dict[str, Appliance]:
        """Return all appliances."""
        return self.appliances

    def get_appliance_ids(self) -> list[str]:
        """Return all appliance ids."""
        return list(self.appliances)
