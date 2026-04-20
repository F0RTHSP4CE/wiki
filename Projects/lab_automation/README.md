---
title: Lab equipment automation
description: Remote control and scripting of equipment in electronics room
published: true
date: 2026-04-20T20:53:00.000Z
tags:
editor: markdown
dateCreated: 2026-04-07T01:49:00.000Z
---

# Lab equipment automation
The following equipment is connected to this system:
  - Agilent E3640A power supply (on left table)
  - ITECH IT8512A+ smart load (on left table)
  - RIGOL DS1104Z+ oscilloscope (on left table)

All equipment is controllable from the IoT network and the shared lab PC via the
[SCPI](https://en.wikipedia.org/wiki/Standard_Commands_for_Programmable_Instruments)
command set, giving you the opportunity to automate and acquire data from these
instruments in a coordinated fashion.

## Getting started
The SCPI command set is quite convoluted, but the gist is as follows:
  1. Power up the instruments that you need (PSU, load, and/or scope)
  2. Power up the lab PC
  3. Press the Windows key, search for "lxi"
  4. Open the installed `lxi-gui` application
  5. Resize the window to full screen to show the left menu
  6. In the left menu, select the instrument to test
  7. In the text box, enter `*idn?` and press Enter
  8. The instrument should reply with its identification string

`*IDN?` is the most basic SCPI command. They are case-insensitive, meaning
`*idn?` is fine. The question mark at the end specifies that we expect a reply
to ths command. No question mark - no reply. The asterisk refers to the most
basic set of commands (defined in IEEE 488.2).

Sometimes you will see the following weird notation in documentation:
```
:MEASure:VOLTage?
```

You are not required to type out the case like this. This notation just means
that the characters in caps are required for the instrument to recognize a
shorthand. For example, the above means that all of the following are
recognized:
```
:meas:volt?
:measure:volt?
:measu:voltag?
:MeAs:VoLtAgE?
```

The colons are path separators in the tree of commands. Try to imagine them as
slashes in your head:
```
:MEASure:VOLTage? -> /measure/voltage
:MEASure:CURRent? -> /measure/current
```

Like in UNIX, a colon in the beginning specifies taking the root as the starting
point.

You can issue multiple commands with a common parent:
```
:MEASure:VOLTage?;CURRent?
```
  1. The first command is `:meas:volt?`
  2. Then, a semicolon to separate the commands
  3. The second command is `:meas:curr?`. `CURRent?` is relative to the
     next-to-last node in the previous command. 

SCPI is quite cryptic, but in the end it lets you expressively shorten commands
like follows:
```
:MEASure:VOLTage?
:MEASure:CURRent?
->
:meas:volt?;curr?
```

Unfortunately, aside from some very basic set of commands, every instrument
defines their own.

## Real-world usage
In the `Documents` folder on the lab PC, there are three PDFs:
  1. PSU user manual (which includes its set of commands)
  2. Smart load programming guide
  3. Oscilloscope programming guide

Go read them and look for the commands that you need.

## Scripting
`lxi-gui` allows you to write Lua scripts to automate these commands.

Here's the setup for the example that follows:
  1. PSU is connected to a DC motor
  2. The motor is fixed in place
  3. A piece of tape is stuck to the shaft
  4. An Arduino black/white optical sensor is looking into the volume where the
     piece of tape passes with each rotation, generating a pulse every time the
     tape passes over it
  5. The sensor is connected to the oscilloscope, allowing it to gather data
     about rotational speed

Assuming this setup, the following script will apply a range of voltages to the
motor, measure its RPM and plot the corresponding RPM-vs-V graph:
```lua
scope = lxi_connect("10.0.24.119", 5025, nil, 2000, "VXI11")
psu = lxi_connect("10.0.24.121", 2000, nil, 2000, "RAW")

print("scope: " .. lxi_scpi(scope, "*idn?"))
print("psu: " .. lxi_scpi(psu, "*idn?"))

lxi_scpi(scope, ":measure:clear all")
lxi_scpi(scope, ":measure:item frequency,chan1")

lxi_scpi(psu, "output off")
lxi_scpi(psu, "volt:rang high")
lxi_scpi(psu, "apply 0,0.5")
lxi_scpi(psu, "output on")

chart = lxi_chart_new("line", "Motor speed", "Voltage [V]", "Speed [RPM]", 20, 10000, 800)

for volt=1, 20, 0.5 do
  lxi_scpi(psu, "volt " .. volt)
  lxi_sleep(2)
  hz = tonumber(lxi_scpi(scope, ":measure:item? frequency,chan1"))
  if hz > 100000 then -- really big values mean "no data" for this scope
    hz = 0
  end
  rpm = hz * 60
  print(volt .. "V: " .. rpm .. " rpm")
  lxi_chart_plot(chart, volt, rpm)
end

lxi_scpi(psu, "volt 0")

lxi_disconnect(scope)
lxi_disconnect(psu)
```

You can see how this mechanism takes our lab to the next level. Imagine all the
things you can measure and plot with so much ease now! Here are some ideas:
  - a DC-DC converter's efficiency vs output current
  - a DC-DC converter's noise level vs output current
  - charge-discharge curves of a battery at different currents
  - etc!

## Current setup
This is how everything is wired together:
  - `PSU's RS-232 interface` -> `DIY DB9 female-female crossover ("null-modem") cable`
    -> `RS-232 to USB adapter` -> `raw TCP at 10.0.24.121:2000 via RPi`
  - `Load's UART TTL interface` -> `semi-DIY UART to USB adapter`
    -> `raw TCP at 10.0.24.121:2001 via RPi`
  - `Oscilloscope` -> `Ethernet switch`
  - `RPi` -> `Ethernet switch`

## Notes

### ITECH IT8512A+ smart load
The load is connected via a weird interface. It uses the same connector and
pinout as RS-232 (with +15/-15 V on data lines), but uses TTL levels (0/+5 V).
**Only use the specially marked 5V pseudo-RS-232 adapter.**

It's based on an `STM32F103CBT6` microcontroller. It's the same one that's
featured on so-called STM32 "blue pill" boards, but with 128KiB of flash instead
of 64 (`CB` instead of `C8`). A 2.54mm header has been soldered to the main
board for easy flashing; the firmware was dumped and modified to show
"F0RTHSP4CE" instead of "SYSTEM INIT" on startup. Original firmware and option
bytes are in `load_fw.bin` and `load_ob.json`. Modified firmware is in
`load_fw_modified.bin`. Option bytes have not been modified.
