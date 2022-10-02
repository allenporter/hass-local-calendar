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

## Recurring Events

See [RFC5545: Recurrence Rule](https://www.rfc-editor.org/rfc/rfc5545#section-3.3.10) for details
on the rrule specification. You can use [RRULE Tool](https://icalendar.org/rrule-tool.html) to
use a graphical interface to create rules.
