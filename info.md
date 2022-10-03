# Local Calendar

A local calendar with relevant and practical features needed for a home calendar implementation
(e.g. recurring events).

This calendar is compatible with the iCalendar standard rfc5545.

## Creating Events

You may create an event with a service call `local_calendar.create_event`.

Here is an example service call that creates an event every day at a specific time:
```
service: local_calendar.create_event
data:
  summary: Nightly
  rrule: FREQ=DAILY
  start_date_time: "2022-10-02T20:00:00"
  end_date_time: "2022-10-02T22:00:00"
target:
  entity_id: calendar.automation
```

| Field | Type | Description |
| ----- | ---- | ----------- |
| summary | str | The short summarization or title of the event. |
| dtstart | date or datetime | The start date or datetime of the event e.g. `2022-10-02` or `2022-10-02T19:30` |
| dtend | date or datetime | The start date or datetime of the event e.g. `2022-10-03` or `2022-10-02T20:00` |
| description | str | The extended description of the event. |
| rrule | str | An rfc554 recurrence rule e.g. `FREQ=MONTHLY`. See below. |

## Deleting Events

See the service `local_calendar.delete_event` which will let you delete an event. For recurring
events you may delete the entire series, a single instance, or an instance and all following
events.

| Field | Type | Description |
| ----- | ---- | ----------- |
| uid | str | The unique identifier of the event and all events in the recurring series) |
| recurrence_id | str | When specified, refers to a specific instance of a recurring event |
| recurrence_range | str | When specified as `THISANDFUTURE` also deletes future recurring events |

## Recurring Events

See [RFC5545: Recurrence Rule](https://www.rfc-editor.org/rfc/rfc5545#section-3.3.10) for details
on the rrule specification. You can use [RRULE Tool](https://icalendar.org/rrule-tool.html) to
use a graphical interface to create rules.
