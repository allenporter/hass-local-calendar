"""Tests for calendar platform of local calendar."""

import datetime
import urllib
import zoneinfo
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from pathlib import Path
from typing import Any
from unittest.mock import patch

import homeassistant.util.dt as dt_util
import pytest
from aiohttp import ClientSession, ClientWebSocketResponse
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import DATE_STR_FORMAT
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.local_calendar import LocalCalendarStore
from custom_components.local_calendar.const import CONF_CALENDAR_NAME, DOMAIN

CALENDAR_NAME = "Light Schedule"
FRIENDLY_NAME = "Light schedule"
TEST_ENTITY = "calendar.light_schedule"


class FakeStore(LocalCalendarStore):
    """Mock storage implementation."""

    def __init__(self, hass: HomeAssistant, path: Path) -> None:
        """Initialize FakeStore."""
        super().__init__(hass, path)
        self._content = ""

    def _load(self) -> str:
        """Read from calendar storage."""
        return self._content

    def _store(self, ics_content: str) -> None:
        """Persist the calendar storage."""
        self._content = ics_content


@pytest.fixture(name="store", autouse=True)
def mock_store() -> None:
    """Test cleanup, remove any media storage persisted during the test."""

    def new_store(hass: HomeAssistant, path: Path) -> FakeStore:
        return FakeStore(hass, path)

    with patch("custom_components.local_calendar.LocalCalendarStore", new=new_store):
        yield


@pytest.fixture(autouse=True)
def set_time_zone(hass: HomeAssistant):
    """Set the time zone for the tests."""
    # Set our timezone to CST/Regina so we can check calculations
    # This keeps UTC-6 all year round
    hass.config.set_time_zone("America/Regina")
    with patch(
        "ical.util.local_timezone", return_value=zoneinfo.ZoneInfo("America/Regina")
    ):
        yield


@pytest.fixture(name="config_entry")
def mock_config_entry() -> MockConfigEntry:
    """Fixture for mock configuration entry."""
    return MockConfigEntry(domain=DOMAIN, data={CONF_CALENDAR_NAME: CALENDAR_NAME})


@pytest.fixture(name="_setup_integration")
async def setup_integration(
    hass: HomeAssistant, config_entry: MockConfigEntry, enable_custom_integrations
) -> None:
    """Set up the integration."""
    _ = enable_custom_integrations
    config_entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()


@pytest.fixture(name="create_event")
def create_event_fixture(
    hass: HomeAssistant,
) -> Callable[[dict[str, Any]], Awaitable[None]]:
    """Fixture to simplify creating events for tests."""

    async def _create(data: dict[str, Any]) -> None:
        await hass.services.async_call(
            DOMAIN,
            "create_event",
            data,
            target={"entity_id": TEST_ENTITY},
            blocking=True,
        )

    return _create


@pytest.fixture(name="delete_event")
def delete_event_fixture(
    hass: HomeAssistant,
) -> Callable[[dict[str, Any]], Awaitable[None]]:
    """Fixture to simplify deleting events for tests."""

    async def _delete(data: dict[str, Any]) -> None:
        await hass.services.async_call(
            DOMAIN,
            "delete_event",
            data,
            target={"entity_id": TEST_ENTITY},
            blocking=True,
        )

    return _delete


GetEventsFn = Callable[[str, str], Awaitable[dict[str, Any]]]


@pytest.fixture(name="get_events")
def get_events_fixture(
    hass_client: Callable[..., Awaitable[ClientSession]]
) -> GetEventsFn:
    """Fetch calendar events from the HTTP API."""

    async def _fetch(start: str, end: str) -> None:
        client = await hass_client()
        response = await client.get(
            f"/api/calendars/{TEST_ENTITY}?start={urllib.parse.quote(start)}"
            f"&end={urllib.parse.quote(end)}"
        )
        assert response.status == HTTPStatus.OK
        return await response.json()

    return _fetch


def event_fields(data: dict[str, str]) -> dict[str, str]:
    """Filter event API response to minimum fields."""
    return {k: data.get(k) for k in ["summary", "start", "end"] if data.get(k)}


async def test_empty_calendar(hass, _setup_integration, get_events):
    """Test querying the API and fetching events."""
    events = await get_events("1997-07-14T00:00:00", "1997-07-16T00:00:00")
    assert len(events) == 0

    state = hass.states.get(TEST_ENTITY)
    assert state.name == FRIENDLY_NAME
    assert state.state == STATE_OFF
    assert dict(state.attributes) == {
        "friendly_name": FRIENDLY_NAME,
    }


async def test_api_date_time_event(_setup_integration, create_event, get_events):
    """Test an event with a start/end date time."""
    await create_event(
        {
            "summary": "Bastille Day Party",
            "dtstart": "1997-07-14T17:00:00+00:00",
            "dtend": "1997-07-15T04:00:00+00:00",
        }
    )

    events = await get_events("1997-07-14T00:00:00Z", "1997-07-16T00:00:00Z")
    assert list(map(event_fields, events)) == [
        {
            "summary": "Bastille Day Party",
            "start": {"dateTime": "1997-07-14T11:00:00-06:00"},
            "end": {"dateTime": "1997-07-14T22:00:00-06:00"},
        }
    ]

    # Time range before event
    events = await get_events("1997-07-13T00:00:00Z", "1997-07-14T16:00:00Z")
    assert len(events) == 0
    # Time range after event
    events = await get_events("1997-07-15T05:00:00Z", "1997-07-15T06:00:00Z")
    assert len(events) == 0

    # Overlap with event start
    events = await get_events("1997-07-13T00:00:00Z", "1997-07-14T18:00:00Z")
    assert len(events) == 1
    # Overlap with event end
    events = await get_events("1997-07-15T03:00:00Z", "1997-07-15T06:00:00Z")
    assert len(events) == 1


async def test_api_date_event(_setup_integration, create_event, get_events):
    """Test an event with a start/end date all day event."""
    await create_event(
        {
            "summary": "Festival International de Jazz de Montreal",
            "dtstart": "2007-06-28",
            "dtend": "2007-07-09",
        }
    )

    events = await get_events("2007-06-20T00:00:00", "2007-07-20T00:00:00")
    assert list(map(event_fields, events)) == [
        {
            "summary": "Festival International de Jazz de Montreal",
            "start": {"date": "2007-06-28"},
            "end": {"date": "2007-07-09"},
        }
    ]

    # Time range before event (timezone is -6)
    events = await get_events("2007-06-26T00:00:00Z", "2007-06-28T01:00:00Z")
    assert len(events) == 0
    # Time range after event
    events = await get_events("2007-07-10T00:00:00Z", "2007-07-11T00:00:00Z")
    assert len(events) == 0

    # Overlap with event start (timezone is -6)
    events = await get_events("2007-06-26T00:00:00Z", "2007-06-28T08:00:00Z")
    assert len(events) == 1
    # Overlap with event end
    events = await get_events("2007-07-09T00:00:00Z", "2007-07-11T00:00:00Z")
    assert len(events) == 1


async def test_active_event(hass, _setup_integration, create_event):
    """Test an event with a start/end date time."""
    start = dt_util.now() - datetime.timedelta(minutes=30)
    end = dt_util.now() + datetime.timedelta(minutes=30)
    await create_event(
        {
            "summary": "Evening lights",
            "dtstart": start,
            "dtend": end,
        }
    )

    state = hass.states.get(TEST_ENTITY)
    assert state.name == FRIENDLY_NAME
    assert state.state == STATE_ON
    assert dict(state.attributes) == {
        "friendly_name": FRIENDLY_NAME,
        "message": "Evening lights",
        "all_day": False,
        "description": "",
        "location": "",
        "start_time": start.strftime(DATE_STR_FORMAT),
        "end_time": end.strftime(DATE_STR_FORMAT),
    }


async def test_upcoming_event(hass, _setup_integration, create_event):
    """Test an event with a start/end date time."""
    start = dt_util.now() + datetime.timedelta(days=1)
    end = dt_util.now() + datetime.timedelta(days=1, hours=1)
    await create_event(
        {
            "summary": "Evening lights",
            "dtstart": start,
            "dtend": end,
        }
    )

    state = hass.states.get(TEST_ENTITY)
    assert state.name == FRIENDLY_NAME
    assert state.state == STATE_OFF
    assert dict(state.attributes) == {
        "friendly_name": FRIENDLY_NAME,
        "message": "Evening lights",
        "all_day": False,
        "description": "",
        "location": "",
        "start_time": start.strftime(DATE_STR_FORMAT),
        "end_time": end.strftime(DATE_STR_FORMAT),
    }


async def test_recurring_event(_setup_integration, create_event, get_events):
    """Test an event with a recurrence rule."""
    await create_event(
        {
            "summary": "Monday meeting",
            "dtstart": "2022-08-29T09:00:00",
            "dtend": "2022-08-29T10:00:00",
            "rrule": "FREQ=WEEKLY",
        }
    )

    events = await get_events("2022-08-20T00:00:00", "2022-09-20T00:00:00")
    assert list(map(event_fields, events)) == [
        {
            "summary": "Monday meeting",
            "start": {"dateTime": "2022-08-29T09:00:00-06:00"},
            "end": {"dateTime": "2022-08-29T10:00:00-06:00"},
        },
        {
            "summary": "Monday meeting",
            "start": {"dateTime": "2022-09-05T09:00:00-06:00"},
            "end": {"dateTime": "2022-09-05T10:00:00-06:00"},
        },
        {
            "summary": "Monday meeting",
            "start": {"dateTime": "2022-09-12T09:00:00-06:00"},
            "end": {"dateTime": "2022-09-12T10:00:00-06:00"},
        },
        {
            "summary": "Monday meeting",
            "start": {"dateTime": "2022-09-19T09:00:00-06:00"},
            "end": {"dateTime": "2022-09-19T10:00:00-06:00"},
        },
    ]


class Client:
    """Test client with helper methods for calendar websocket."""

    def __init__(self, client):
        """Initialize Client."""
        self.client = client
        self._id = 0

    async def cmd(self, cmd: str, payload: dict[str, Any] = None) -> dict[str, Any]:
        """Send a command and receive the json result."""
        self._id += 1
        await self.client.send_json(
            {
                "id": self._id,
                "type": f"calendar/event/{cmd}",
                **(payload if payload is not None else {}),
            }
        )
        resp = await self.client.receive_json()
        assert resp.get("id") == self._id
        return resp

    async def cmd_result(self, cmd: str, payload: dict[str, Any] = None) -> Any:
        """Send a command and parse the result."""
        resp = await self.cmd(cmd, payload)
        assert resp.get("success")
        assert resp.get("type") == "result"
        return resp.get("result")


ClientFixture = Callable[[], Client]


@pytest.fixture(name="ws_client")
async def mock_ws_client(
    hass_ws_client: Callable[[...], ClientWebSocketResponse]
) -> ClientFixture:
    """Fixture for creating the test websocket client."""

    async def create_client() -> Client:
        ws_client = await hass_ws_client()
        return Client(ws_client)

    return create_client


async def test_websocket_create(
    ws_client: ClientFixture, _setup_integration: None, get_events: GetEventsFn
):
    """Test websocket create command."""
    client = await ws_client()
    await client.cmd_result(
        "create",
        {
            "entity_id": TEST_ENTITY,
            "event": {
                "summary": "Bastille Day Party",
                "dtstart": "1997-07-14T17:00:00+00:00",
                "dtend": "1997-07-15T04:00:00+00:00",
            },
        },
    )
    events = await get_events("1997-07-14T00:00:00", "1997-07-16T00:00:00")
    assert list(map(event_fields, events)) == [
        {
            "summary": "Bastille Day Party",
            "start": {"dateTime": "1997-07-14T11:00:00-06:00"},
            "end": {"dateTime": "1997-07-14T22:00:00-06:00"},
        }
    ]


async def test_websocket_delete(
    ws_client: ClientFixture, _setup_integration: None, get_events: GetEventsFn
):
    """Test websocket delete command."""
    client = await ws_client()
    result = await client.cmd_result(
        "create",
        {
            "entity_id": TEST_ENTITY,
            "event": {
                "summary": "Bastille Day Party",
                "dtstart": "1997-07-14T17:00:00+00:00",
                "dtend": "1997-07-15T04:00:00+00:00",
            },
        },
    )
    assert "uid" in result

    events = await get_events("1997-07-14T00:00:00", "1997-07-16T00:00:00")
    assert list(map(event_fields, events)) == [
        {
            "summary": "Bastille Day Party",
            "start": {"dateTime": "1997-07-14T11:00:00-06:00"},
            "end": {"dateTime": "1997-07-14T22:00:00-06:00"},
        }
    ]

    # Delete the event
    result = await client.cmd_result(
        "delete",
        {
            "entity_id": TEST_ENTITY,
            "uid": result["uid"],
        },
    )
    events = await get_events("1997-07-14T00:00:00", "1997-07-16T00:00:00")
    assert not list(map(event_fields, events))


async def test_websocket_delete_recurring(
    ws_client: ClientFixture, _setup_integration: None, get_events: GetEventsFn
):
    """Test deleting a recurring event."""
    client = await ws_client()
    result = await client.cmd_result(
        "create",
        {
            "entity_id": TEST_ENTITY,
            "event": {
                "summary": "Morning Routine",
                "dtstart": "2022-08-22T08:30:00",
                "dtend": "2022-08-22T09:00:00",
                "rrule": "FREQ=DAILY",
            },
        },
    )
    assert "uid" in result
    uid = result["uid"]

    events = await get_events("2022-08-22T00:00:00", "2022-08-26T00:00:00")
    assert list(map(event_fields, events)) == [
        {
            "summary": "Morning Routine",
            "start": {"dateTime": "2022-08-22T08:30:00-06:00"},
            "end": {"dateTime": "2022-08-22T09:00:00-06:00"},
        },
        {
            "summary": "Morning Routine",
            "start": {"dateTime": "2022-08-23T08:30:00-06:00"},
            "end": {"dateTime": "2022-08-23T09:00:00-06:00"},
        },
        {
            "summary": "Morning Routine",
            "start": {"dateTime": "2022-08-24T08:30:00-06:00"},
            "end": {"dateTime": "2022-08-24T09:00:00-06:00"},
        },
        {
            "summary": "Morning Routine",
            "start": {"dateTime": "2022-08-25T08:30:00-06:00"},
            "end": {"dateTime": "2022-08-25T09:00:00-06:00"},
        },
    ]

    # Cancel a single instance and confirm it was removed
    await client.cmd_result(
        "delete",
        {
            "entity_id": TEST_ENTITY,
            "recurrence_id": "20220824T083000",
            "uid": uid,
        },
    )
    events = await get_events("2022-08-22T00:00:00", "2022-08-26T00:00:00")
    assert list(map(event_fields, events)) == [
        {
            "summary": "Morning Routine",
            "start": {"dateTime": "2022-08-22T08:30:00-06:00"},
            "end": {"dateTime": "2022-08-22T09:00:00-06:00"},
        },
        {
            "summary": "Morning Routine",
            "start": {"dateTime": "2022-08-23T08:30:00-06:00"},
            "end": {"dateTime": "2022-08-23T09:00:00-06:00"},
        },
        {
            "summary": "Morning Routine",
            "start": {"dateTime": "2022-08-25T08:30:00-06:00"},
            "end": {"dateTime": "2022-08-25T09:00:00-06:00"},
        },
    ]

    # Delete all and future and confirm multiple were removed
    await client.cmd_result(
        "delete",
        {
            "entity_id": TEST_ENTITY,
            "uid": uid,
            "recurrence_id": "20220823T083000",
            "recurrence_range": "THISANDFUTURE",
        },
    )
    events = await get_events("2022-08-22T00:00:00", "2022-08-26T00:00:00")
    assert list(map(event_fields, events)) == [
        {
            "summary": "Morning Routine",
            "start": {"dateTime": "2022-08-22T08:30:00-06:00"},
            "end": {"dateTime": "2022-08-22T09:00:00-06:00"},
        },
    ]


async def test_websocket_update(
    ws_client: ClientFixture, _setup_integration: None, get_events: GetEventsFn
):
    """Test websocket update command."""
    client = await ws_client()
    result = await client.cmd_result(
        "create",
        {
            "entity_id": TEST_ENTITY,
            "event": {
                "summary": "Bastille Day Party",
                "dtstart": "1997-07-14T17:00:00+00:00",
                "dtend": "1997-07-15T04:00:00+00:00",
            },
        },
    )
    assert "uid" in result

    # Update the event summary
    result = await client.cmd_result(
        "update",
        {
            "entity_id": TEST_ENTITY,
            "event": {
                "uid": result["uid"],
                "summary": "July Party",
            },
        },
    )
    events = await get_events("1997-07-14T00:00:00", "1997-07-16T00:00:00")
    assert list(map(event_fields, events)) == [
        {
            "summary": "July Party",
            "start": {"dateTime": "1997-07-14T11:00:00-06:00"},
            "end": {"dateTime": "1997-07-14T22:00:00-06:00"},
        }
    ]


async def test_delete_event_service(
    ws_client: ClientFixture,
    _setup_integration: None,
    get_events: GetEventsFn,
    delete_event: Callable[[dict[str, Any]], Awaitable[None]],
):
    """Test delete event service."""
    client = await ws_client()
    result = await client.cmd_result(
        "create",
        {
            "entity_id": TEST_ENTITY,
            "event": {
                "summary": "Bastille Day Party",
                "dtstart": "1997-07-14T17:00:00+00:00",
                "dtend": "1997-07-15T04:00:00+00:00",
            },
        },
    )
    assert "uid" in result
    uid = result["uid"]

    events = await get_events("1997-07-14T00:00:00", "1997-07-16T00:00:00")
    assert list(map(event_fields, events)) == [
        {
            "summary": "Bastille Day Party",
            "start": {"dateTime": "1997-07-14T11:00:00-06:00"},
            "end": {"dateTime": "1997-07-14T22:00:00-06:00"},
        }
    ]

    # Delete the event
    await delete_event(
        {
            "entity_id": TEST_ENTITY,
            "uid": uid,
        },
    )
    events = await get_events("1997-07-14T00:00:00", "1997-07-16T00:00:00")
    assert not list(map(event_fields, events))


async def test_delete_event_recurring(
    ws_client: ClientFixture,
    _setup_integration: None,
    get_events: GetEventsFn,
    delete_event: Callable[[dict[str, Any]], Awaitable[None]],
):
    """Test deleting a recurring event."""
    client = await ws_client()
    result = await client.cmd_result(
        "create",
        {
            "entity_id": TEST_ENTITY,
            "event": {
                "summary": "Morning Routine",
                "dtstart": "2022-08-22T08:30:00",
                "dtend": "2022-08-22T09:00:00",
                "rrule": "FREQ=DAILY",
            },
        },
    )
    assert "uid" in result
    uid = result["uid"]

    events = await get_events("2022-08-22T00:00:00", "2022-08-26T00:00:00")
    assert list(map(event_fields, events)) == [
        {
            "summary": "Morning Routine",
            "start": {"dateTime": "2022-08-22T08:30:00-06:00"},
            "end": {"dateTime": "2022-08-22T09:00:00-06:00"},
        },
        {
            "summary": "Morning Routine",
            "start": {"dateTime": "2022-08-23T08:30:00-06:00"},
            "end": {"dateTime": "2022-08-23T09:00:00-06:00"},
        },
        {
            "summary": "Morning Routine",
            "start": {"dateTime": "2022-08-24T08:30:00-06:00"},
            "end": {"dateTime": "2022-08-24T09:00:00-06:00"},
        },
        {
            "summary": "Morning Routine",
            "start": {"dateTime": "2022-08-25T08:30:00-06:00"},
            "end": {"dateTime": "2022-08-25T09:00:00-06:00"},
        },
    ]

    # Cancel a single instance and confirm it was removed
    await delete_event(
        {
            "entity_id": TEST_ENTITY,
            "recurrence_id": "20220824T083000",
            "uid": uid,
        }
    )
    events = await get_events("2022-08-22T00:00:00", "2022-08-26T00:00:00")
    assert list(map(event_fields, events)) == [
        {
            "summary": "Morning Routine",
            "start": {"dateTime": "2022-08-22T08:30:00-06:00"},
            "end": {"dateTime": "2022-08-22T09:00:00-06:00"},
        },
        {
            "summary": "Morning Routine",
            "start": {"dateTime": "2022-08-23T08:30:00-06:00"},
            "end": {"dateTime": "2022-08-23T09:00:00-06:00"},
        },
        {
            "summary": "Morning Routine",
            "start": {"dateTime": "2022-08-25T08:30:00-06:00"},
            "end": {"dateTime": "2022-08-25T09:00:00-06:00"},
        },
    ]

    # Delete all and future and confirm multiple were removed
    await delete_event(
        {
            "entity_id": TEST_ENTITY,
            "uid": uid,
            "recurrence_id": "20220823T083000",
            "recurrence_range": "THISANDFUTURE",
        }
    )
    events = await get_events("2022-08-22T00:00:00", "2022-08-26T00:00:00")
    assert list(map(event_fields, events)) == [
        {
            "summary": "Morning Routine",
            "start": {"dateTime": "2022-08-22T08:30:00-06:00"},
            "end": {"dateTime": "2022-08-22T09:00:00-06:00"},
        },
    ]
