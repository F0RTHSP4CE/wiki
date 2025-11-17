---
title: Butler (Smart Door, Physical Access Control System)
description: 
published: true
date: 2023-09-21T08:41:14.288Z
tags: 
editor: markdown
dateCreated: 2023-09-15T06:27:33.709Z
---

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
Python script to check local storage for NFC match. Works only with static NFC for now.
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
