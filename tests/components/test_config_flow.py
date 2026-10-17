"""Tests for the Kestrel config and options flows."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.kestrel.const import (
    CONF_FAMILY,
    CONF_MODEL_CODE,
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)

from .conftest import (
    DROP_ADDRESS,
    DROP_MODEL_CODE,
    DROP_NAME,
    DROP_SERVICE_INFO,
    SPEEDCOACH_SERVICE_INFO,
    FakeKestrelBleDevice,
    inject_bluetooth_service_info,
    make_service_info,
)


async def test_bluetooth_discovery(
    hass: HomeAssistant, setup_bluetooth: None, mock_device: FakeKestrelBleDevice
) -> None:
    """A discovered DROP is confirmed and creates an entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=DROP_SERVICE_INFO,
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"
    assert result["description_placeholders"] == {"name": DROP_NAME}

    inject_bluetooth_service_info(hass, DROP_SERVICE_INFO)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == DROP_NAME
    assert result["data"] == {
        CONF_ADDRESS: DROP_ADDRESS,
        CONF_FAMILY: "drop",
        CONF_MODEL_CODE: DROP_MODEL_CODE,
    }
    assert result["options"] == {CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL}
    assert result["result"].unique_id == DROP_ADDRESS


async def test_bluetooth_discovery_already_configured(
    hass: HomeAssistant, setup_bluetooth: None, mock_config_entry: MockConfigEntry
) -> None:
    """Discovery aborts when the address is already set up."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=DROP_SERVICE_INFO,
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_bluetooth_discovery_not_supported(
    hass: HomeAssistant, setup_bluetooth: None
) -> None:
    """Non-weather NK products (e.g. a SpeedCoach) are rejected."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_BLUETOOTH},
        data=SPEEDCOACH_SERVICE_INFO,
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "not_supported"


async def test_user_flow(
    hass: HomeAssistant, setup_bluetooth: None, mock_device: FakeKestrelBleDevice
) -> None:
    """The user step lists discovered weather devices only."""
    inject_bluetooth_service_info(hass, DROP_SERVICE_INFO)
    inject_bluetooth_service_info(hass, SPEEDCOACH_SERVICE_INFO)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    options = result["data_schema"].schema[CONF_ADDRESS].container
    assert list(options) == [DROP_ADDRESS]
    assert DROP_NAME in options[DROP_ADDRESS]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={CONF_ADDRESS: DROP_ADDRESS}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == DROP_NAME
    assert result["data"][CONF_ADDRESS] == DROP_ADDRESS
    assert result["result"].unique_id == DROP_ADDRESS


async def test_user_flow_no_devices(hass: HomeAssistant, setup_bluetooth: None) -> None:
    """The user step aborts when nothing supported has been seen."""
    inject_bluetooth_service_info(hass, SPEEDCOACH_SERVICE_INFO)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_user_flow_skips_configured(
    hass: HomeAssistant, setup_bluetooth: None, mock_config_entry: MockConfigEntry
) -> None:
    """Already configured devices are not offered again."""
    mock_config_entry.add_to_hass(hass)
    inject_bluetooth_service_info(hass, DROP_SERVICE_INFO)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_options_flow(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_device: FakeKestrelBleDevice,
) -> None:
    """Changing the poll interval updates options and reloads the entry."""
    entry = init_integration
    assert mock_device.async_poll.await_count == 1

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={CONF_POLL_INTERVAL: 120}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {CONF_POLL_INTERVAL: 120}
    assert entry.state is config_entries.ConfigEntryState.LOADED
    # Reload created a new device wrapper and polled again.
    assert mock_device.async_poll.await_count == 1
    assert entry.runtime_data.poll_interval == 120


async def test_bluetooth_discovery_title_strips_nul_padding(
    hass: HomeAssistant, mock_bluetooth: None
) -> None:
    """The flow title must not carry the DROP's NUL padding."""
    info = make_service_info(name="D3 - 3103865" + "\x00" * 9)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=info
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "bluetooth_confirm"
    flow = hass.config_entries.flow.async_get(result["flow_id"])
    assert flow["context"]["title_placeholders"]["name"] == "D3 - 3103865"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "D3 - 3103865"
