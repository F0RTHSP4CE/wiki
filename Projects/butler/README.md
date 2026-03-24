---
title: Butler (Smart Door, Physical Access Control System)
description: Entrance access control system
published: true
date: 2026-03-24T12:00:00.000Z
tags:
editor: markdown
dateCreated: 2023-09-15T06:27:33.709Z
---

# Butler

F0's door controller has gone through multiple rewrites.

The current public history is:

1. the original Butler stack handled the first generation of door control;
2. it was later rewritten by `@rozetkinrobot` to support NFC and bank cards;
3. after that it was rewritten again by `@Mike_Went`.

The current repo is [F0RTHSP4CE/usbutler](https://github.com/F0RTHSP4CE/usbutler).

## Current System Summary

`usbutler/` is the latest Butler implementation.

At a high level, it is a hardware-backed access-control system centered on one FastAPI app plus a few background device loops.

### Runtime Shape

- `docker-compose.yml` runs a privileged container with host networking and direct access to USB smart-card devices and `/dev/gpiochip0`
- `Dockerfile` installs `pyscard`, `pcscd`, `gpiod`, FastAPI, and SQLAlchemy
- `supervisord.conf` starts `pcscd`, a udev monitor script, and `uvicorn`
- `app/main.py` creates DB tables, initializes shared services, starts GPIO button monitoring, starts the background card-polling thread, and mounts the HTTP routers

### Application Layout

- routers in `app/routers/` define HTTP boundaries for users, doors, identifiers, POS, and UI
- `app/dependencies.py` is the main composition root for auth, DB sessions, and request-scoped services
- `app/services/` contains both DB-oriented services and hardware-facing services
- SQLAlchemy persistence lives in `app/database.py` plus models in `app/models/`
- API contracts live in `app/schemas/`
- the admin UI is server-rendered Jinja in `app/templates/`

### Main Control Flows

- card flow: NFC reader polling reads a PAN or UID, auth maps it to an active user, Butler opens the default door, records a `DoorEvent`, and sends a Telegram notification
- button flow: GPIO monitoring watches configured door pins, debounces presses, stores `BUTTON` events, and sends notifications

### Auth Split

- API routes use `X-API-Key`
- POS routes use `X-POS-Secret`
- UI routes use an admin cookie

The architecture notes below describe the older design and should be treated as partial historical documentation, not as a precise description of the current software layout.

# Architecture
## Hardware part
### Lock itself
Lock on the door with solenoid.
When you send 12v on it, it opens, but impulse should be short, less than 1sec. We use 0.1 sec now.

Lock mechanic has some specific, that, if you open it by electric trigger, it's remains open, until the door was not phisically opened and closed again. That's because there's spring inside and it need to be winded.

On power loss lock remains locked.

Lock could be opened by mechanical key outside, but it's only for emergency.

### Devices
There is RaspberryPi, relay, and NFC-reader.
System gets 12v for relay and 5v by stepDown DCDC for RaspberryPi.
Power is hooked with recovery power system in basement, so if system is off, ACS is off (and lock is locked).
About power recovery system you should ask Andrey.


## Software part
There're bunch of services here.

###lock script
https://github.com/f0rthsp4ce/doorLock/blob/dev/README.md
Main Python script to send relay a trigger and trigger notify scripts

###NFC-reader
https://github.com/f0rthsp4ce/doorLock/blob/dev/bin/butlerNFC/README.md
Earlier Python script to check local storage for NFC match.
Triggers **lock script**

###ESC button
https://github.com/f0rthsp4ce/doorLock/blob/dev/bin/buttonExit/README.md
Anti-jig python script for door open by button on the wall near the door.
Triggers **lock script**

###ButlerWeb
https://github.com/f0rthsp4ce/butlerWeb/blob/main/README.md
Python Flask web-service to open the door by auth users.
Has it's own local storage.
Triggers **lock script**
Button on the table in main room (known as door_button_clicker) uses ButlerWeb account.

###ButlerTg (depreceated)
https://github.com/f0rthsp4ce/doorLock/blob/dev/tg-bot/README.md
GoLang service to tigger **lock script**, now is out of use.
