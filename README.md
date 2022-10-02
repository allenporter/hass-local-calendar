# Home Assistant Local Calendar

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)

This repo is a Local Calendar custom component for a Home Assistant.

The calendar is implemented using an rfc5545 python library, aiming to
be compatible with nearly all relevant features for a modern home local
calendar.  See [ical](https://github.com/allenporter/ical) for details
on the underlying python library.

## Development

Setup development environment

```
$ python3 -m venv venv
$ source venv/bin/activate
$ pip3 install -r requirements_dev.txt
```

Run the tests:
```
$ pytest
```
