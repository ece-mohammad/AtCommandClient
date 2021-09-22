# AtCmdClient

ATCmdClient is a python package to send and receive AT commands, 
over a serial port (UART), to control a device that supports 
AT commands, like GSM modules (SIM800, a9G, etc), 
ESP32 and its variants, Bluetooth modules, and others.


## Table Of Contents

<!-- MarkdownTOC -->

- [Terminology](#terminology)
- [Introduction to AT Commands](#introduction-to-at-commands)
    - [Commands](#commands)
        - [Read Command](#read-command)
        - [Write Command](#write-command)
        - [Test Command](#test-command)
        - [Execute Command](#execute-command)
    - [Responses](#responses)
        - [Final Response](#final-response)
        - [Information Response](#information-response)
        - [Unsolicited Response](#unsolicited-response)
    - [General Syntax](#general-syntax)
        - [Number Type Parameters](#number-type-parameters)
        - [String Type Parameters](#string-type-parameters)
- [Classes](#classes)
    - [AtCommandStatus](#atcommandstatus)
    - [AtStringMatchingRule](#atstringmatchingrule)
    - [AtEventType](#ateventtype)
    - [AtString](#atstring)
        - [Attributes](#attributes)
        - [Methods](#methods)
    - [AtCommandResponse](#atcommandresponse)
        - [Attributes](#attributes-1)
        - [Examples](#examples)
    - [AtEvent](#atevent)
        - [Attributes](#attributes-2)
        - [Examples](#examples-1)
    - [AtCommand](#atcommand)
        - [Attributes](#attributes-3)
        - [Examples](#examples-2)
    - [AtCommandClient](#atcommandclient)
        - [Attributes](#attributes-4)
        - [Methods](#methods-1)
        - [Examples](#examples-3)
- [How To And Examples](#how-to-and-examples)

<!-- /MarkdownTOC -->


<a id="terminology"></a>
## Terminology

<a id="at-client"></a>
**AT Client**: A device that sends AT commands to an *AT server*, for example: a PC or a micro-controller

**AT Server**: A device that exposes some of its functionality through AT commands, can receive on a communication interface (usually, serial interface, UART). It receives AT commands and sends back responses to the client

**AT Event**: An unsolicited response sent by the AT server to the AT client

**Note**
> 1. I adopted the name client, because in AT commands there are 2 devices, one device that sends AT commands and the other processes them and send responses if needed. That reminded me of client-sever relation, and hence, the name. It's probably not accurate, but it's what I can think of right now.
> 2. AT commands are a subset of Heyes commands, which were made to control modems. In networking, modems are a type of DCE (Date Circuit/Carrier/Communication Equipment), and end devices like PCs are called DTE (Data Terminal Equipment). The AT client will run on a DTE, and the AT server will be running on a DCE.


<a id="introduction-to-at-commands"></a>
## Introduction to AT Commands

AT commands are a form of RPC (Remote Procedure Call), where a server exposes some internal functionalities or processes through a well defined API and clients can request the result of running a function or a process with some parameters from the server.

At commands follow the request-response pattern. The client sends a request to the server, and the server sends back a response indicating the command execution status either success or failure.

AT commands do not have a well defined standardized command set, so manufacturers usually tailor AT command set to their devices. That means adding new extended commands, removing basic/extended commands, grouping command types (set and execute, for example), and removing test commands for some or even all the device's supported commands. 

While that might seem bad at first, it makes sense to trim unwanted functionalities to reduce the At commands set, and the size of the program on the device. That allows AT commands to be used on a multitude of different devices, like GSM modules, Bluetooth modules, WiFi, Ethernet and more.

<a id="commands"></a>
### Commands

AT Commands are divided into 2 categories:
- **Basic Commands**: Commands that does *NOT start* with a `+`, like `AT` (check AT, supported by all devices that I know of), `ATE` (command echo,  supported by all devices I know of), 
- **Extended Commands**: Commands that does *start* with a `+`, like `AT+GMR`, `AT+GMI`, `AT+CIPSEND`.

The commands are divided in functionality to 4 types:
- Read (Query) Command.
- Set Command
- Test Command
- Execute Command

<a id="read-command"></a>
#### Read Command

Request the current value of some parameter or state

**Format**

```text
AT+<cmd>?
```

**Examples**

- `AT+uART_CR?`: read current UART configurations (ESP8266 and its variants)
- `AT+CCLK?`: read current date and time (Nordic nRF devices, A9G GSM module)

<a id="write-command"></a>
#### Write Command

Set the value of a parameter or state

**Format**
```text
AT+<cmd>=<..>
```

**Examples**

- `AT+UART_CUR=<baudrate>,<databits>,<stopbits>,<parity>,<flowcontrol>` (set current UART configurations, esp8266)


<a id="test-command"></a>
#### Test Command

Get a list of values and ranges supported by the command

**Format**

```text
AT+<cmd>=?
```

**Examples**

- `AT+IPR=?`: Get supported UART baudrates (A9G GSM module)
- `AT+RST=?`: Get supported modes for `RST` command (A9G GSM module)

<a id="execute-command"></a>
#### Execute Command

Request an internal process, and read the associated parameters affected by that process.

**Format**

```text
AT+<cmd>
```

**Examples**
- `AT+CSQ`: return the current network RSSI (Received Signal Strength Indicator) (A9G GSM module)


<a id="responses"></a>
### Responses

There are 3 types of responses:
- Final Response
- Information (Partial) Response
- Unsolicited Response

In AT commands, there is a general response called OK response (`OK\r\n`), that is sent after 

<a id="final-response"></a>
#### Final Response

A response with the *result* of processing a previous request.

**Example**:

```text
>>> AT          # command
<<< OK          # final response
```

<a id="information-response"></a>
#### Information Response

A response with **information** about the processing of previous command. This response is not sent for all commands.

**Example**:

```text
>>> AT+UART_CUR=<...>       # command
<<< +UART_CUR=<...>         # information response
<<< OK                      # final response

```

<a id="unsolicited-response"></a>
#### Unsolicited Response

Un-requested response, a response sent by the device without a previous request. To indicate some state change, like a received call, SMS or data. Sometime referred to as URC (Unsolicited Response Code).
Some URCs are sent periodically, some are only sent only once when the device is reset, and some are sent sporadically when something occurs.
Usually, there is a command to configure periodic URC, usaully to either to enable them, disable them or only report on change.

> unsolicited responses will be referred to as AT events within the code

**Example**:

```text
.
no commands sent
.
<<< +MQTTPUBLISH:1,alpha,10,abcdefghij  # received MQTT publish data on topic alpha
```

<a id="general-syntax"></a>
### General Syntax

- All AT commands data will be terminated with at least 1 special character, the default in most terminals is the `<CR><LR>` or `\r\n` characters, eg:
`command\r\n` and `response\r\n`

- Almost all commands (basic and extended) will start with `AT`, except for very few commands like: `+++`

- AT write commands take parameters after the equal (`=`) sign, commas (`,`) are used to separate multiple parameters. *No* spaces around the commas.

- There are 2 types of parameters, numbers and string.

- Empty string parameters are not omitted, and an empty string (`""`) must be supplied. However, some vendors allow omission of empty string parameters If the parameter is in the middle of the parameters list, the surrounding commas must be present. *Example*: `>>> AT+CMD=p1,p2,p3,p4` and parameter #2 is omitted, the 2nd comma must be present `>>> AT+CMD=p1,,p3,p4`

- Some commands have optional parameters that can be sent only if a value other than default value is needed. 

***Note***:

These rules are general rules and by no means are conclusive. A manufacturer or vendor may have different rules for example, regarding parameters omission, or add more rules. It's *very important* to read the device's datasheet and/or reference manual to understand the device's AT commands.


<a id="number-type-parameters"></a>
#### Number Type Parameters

Number parameters are a sequence of digits representing a decimal number (unless otherwise specified by manufacturer). 
Can include negative sign and zero but, can't lead with a zero unless the number is zero.

**Example**:

```text
>>> AT+IPR=9600     # set UART baudrate (USR-K, Ethernet module)
>>> ATE0            # disable command echo (all AT devices)
>>> AT+CGATT=1      # start network attach (GSM module A9G and SIM800)
```

<a id="string-type-parameters"></a>
#### String Type Parameters

String parameter are a sequence of ASCII characters representing string.
A string of multiple words must be enclosed within double quotes (`"`).
Some manufacturers allow single word strings without the double quotes.

Special characters that must be escaped with backslash (`\`) within the string

| **Character** | **Escape Sequence** |
| :-----------: | :-----------------: |
| backslash character (`\`) | `\\` |
| double quotes (`"`) | `\"` |

Characters can be represented by their ASCII codes in the format `\hh`, 
where `hh` is the hexadecimal ASCII code of the character.

**Example**:

```text
Sending message {"key":"value"} to MQTT topic "topic/data"

>>> AT+MQTTPUB="topic/data","{\"key\":\"value\"}",0,0,0
>>> AT+MQTTPUB="topic/data","{\22key\22:\22value\22}",0,0,0

AT device translates them to:
>>> AT+MQTTPUB="topic/data","{"key":"value"}",0,0,0
>>> AT+MQTTPUB="topic/data","{"key":"value"}",0,0,0
```

<a id="classes"></a>
## Classes


<a id="atcommandstatus"></a>
### AtCommandStatus

An Enum that represents the status of a command after it was sent. 

##### Enum Members

- `AtCommandStatus.Success`: The command as sent and a *success* response 
was received before command timeout

- `AtCommandStatus.Error`: The command was sent and an *error* response 
was received before command timeout

- `AtCommandStatus.Timeout`: The command was sent but no response matching
 success or error responses was received before command timeout


<a id="atstringmatchingrule"></a>
### AtStringMatchingRule

An Enum that represents how a command response is searched for in the received 
response string

##### Enum Members

`AtStringMatchingRule.Regex`: The response string is treated as a Regex pattern, and the command response 
will be a string that matches that Regex pattern within the received response string

`AtStringMatchingRule.Exact`: The response string is treated as is, the command response will be a sub string 
of the received response string


<a id="ateventtype"></a>
### AtEventType

An Enum that describes an AT event recurrence. see [unsolicited response](#unsolicited-response) 
section for more info

##### Enum Members

- `AtEventType.OneTime`: The event will be handled only 1 time, after that it will be removed

- `AtEventType.Reoccurring`: The event will be kept, and handled as many times as the event string is 
matched within the response string


<a id="atstring"></a>
### AtString

```python
AtString(name: str, string: str, matching: AtStringMatchingRule = AtStringMatchingRule.Regex)
```

A  meta class that provides generic named string for AT commands responses and events.

`name`: string name, must be a valid string.

`string`: string pattern.

`matching`: (optional) string matching rule, must be a member of [AtStringMatchingRule](#AtStringMatchingRule)

<a id="attributes"></a>
#### Attributes

- **name**:
The AT string name, used to identify different strings.

- **string**:
The AT response string to search for within the received response string. 
default value is `AtStringMatchingRule.Regex`.

- **match_type**:
String matching type, how `string` is used to detect a command response in
the received response string.

<a id="methods"></a>
#### Methods

```python
AtString.match_string(pattern: str, string: str, match_type: AtStringMatchingRule) -> str
```

Static method that searches for and return the string from `string` that 
matches `pattern`, according to `match_type`. If not string match as found, 
returns an empty string.

- **pattern**: 
Non empty string pattern that is used to search for a matching sting in `string`.

- **string**: 
None empty string that may or may not contain a string that matches `pattern`.

- **match_type**:
Dictates how a `string` is searched for `pattern`. 
If `match_type=AtStringMatchingRule.Exact`, `string` is searched for a sub string
that exactly matches `pattern` (case sensitive).
If `match_type=AtStringMatchingRule.Regex`, `string` is searched for a sub string
that matches `pattern` as a regular expression. Underneath, the method uses
 `re.findall` and returns the first match found.

**Examples**
```python
>>> AtString.match_string("foo", "foo bar", AtStringMatchingRule.Exact)
>>> "foo"
>>> AtString.match_string("baz", "foo bar", AtStringMatchingRule.Exact)
>>> ""
>>> AtString.match_string("\\w+", "foo bar", AtStringMatchingRule.Regex)
>>> "foo"
>>> AtString.match_string("\\+CME ERROR: \\d+", "+CME ERROR: 53", AtStringMatchingRule.Regex)
>>> "CME ERROR: 53"
>>> AtString.match_string("\\d+", "foo bar", AtStringMatchingRule.Regex)
>>> ""
```

<a id="atcommandresponse"></a>
### AtCommandResponse

```python
AtCommandResponse(name: str, 
                  string: str,
                  matching: AtStringMatchingRule = AtStringMatchingRule.Regex)
```

A subclass of `AtString`, provides a named response class for `AtCommand` class.
A response is defined by its `string` and `matching`. A response pattern `string`
can be anything that is sent back in response to the command. But if you're using 
regex, make sure that the regex pattern given in `string` is valid and works properly.

<a id="attributes-1"></a>
#### Attributes

- `name`, `string` and `match_type`. See [AtString](#atstring) for more details.

<a id="examples"></a>
#### Examples

```python
>>> ok_response = AtCommandResponse("Ok Response", "OK\r\n", AtStringMatchingRule.Exact)
>>> prompt_response = AtCommandResponse("Prompt", ">", AtStringMatchingRule.Exact)
>>> time_response = AtCommandResponse("Time Response", "\\+CCLK:\\s*.*", AtStringMatchingRule.Regex)
```

<a id="atevent"></a>
### AtEvent

```python

AtEvent(name: str, string: str, 
        callback: callable[[str, str], None], 
        event_type: AtEventType = AtEventType.OneTime, 
        matching: AtStringMatchingRule = AtStringMatchingRule.Regex)
```

A subclass of `AtString` that provides named response for `AtCommandClient`, 
to handle unsolicited responses. 
Just like normal responses, `AtEvents` have a `name`, `string`, `match_type` 
attributes, and adds to them 2 more attributes: `callback` and `event_type`.

The event occurs when a match with the event string pattern is found 
in the received response. The `callback` with the associated event is called, 
and If the event is a one time event, the client will remove the event.

Events can be added to the client using `add_event` method. 
See [AtCommandClient](#atcommandclient) for more details.

<a id="attributes-2"></a>
#### Attributes

- `name`, `string` and `match_type`. See [AtString](#atstring) for more details.

- `callback`: A function that will be called when the event occurs. The callback 
will be passed the following parameters:

    - `event_string`: The result from `ATString.match_string` of the event that 
    triggered the callback and the response string.
    - `response_string`: The whole response string in which the event string 
    was found.

- `event_type`: An enum of type `AtEventType` that defines the recurrence of 
the event.

<a id="examples-1"></a>
#### Examples

```python
>>> def on_ready(match: str, response_buffer: str):
>>>     print("Ready event received!")
>>>     print(f"match string {match} in {response_buffer}")
>>>
>>> AtEvent("Ready Event", "READY\r\n", on_ready, AtStringMatchingRule.Exact)
>>>
>>> # receive READY\r\n 
>>> # "Ready event received!"
>>> # "match string {match} in {response_buffer}"
>>> # Receive READY\r\n for 2nd time
>>> # ... nothing ...
```

<a id="atcommand"></a>
### AtCommand

```python
AtCommand(name: str, cmd: str,
          success_response: Union[AtCommandResponse, None],
          error_response: Union[List[AtCommandResponse], None] = None,
          timeout: float = 0)
```

A class that provides a description of AT commands.

<a id="attributes-3"></a>
#### Attributes

- `name`: AT command name, used to identify different commands.
Can be an empty string.

- `cmd`: The AT command string that will be sent to the AT modem

- `success_response`: `AtCommandResponse` object, that describes the response that 
which if received, the command will be considered a success. The response string
can be a multi line string, but for simplicity, it should be the last line of 
the command's response.

- `error_response`: A list of `AtCommandResponse` objects, which if any of them 
is received, the command will be considered failed due to the received error.


<a id="examples-2"></a>
#### Examples

```python
>>> ok_response = AtCommandResponse(
>>>         name="OK",
>>>         string="OK\r\n",
>>>         matching=AtStringMatchingRule.Exact
>>> )
>>> 
>>> at_check = AtCommand(
>>>         name="AT Check",
>>>         cmd="AT\r\n",
>>>         success_response=ok_response,
>>>         timeout=1
>>> )
```

<a id="atcommandclient"></a>
### AtCommandClient

```python
AtCommandClient(name: str, uart_handle: serial.Serial)
```

A class that provides AT commands handling over serial port (UART), 
for the client (DTE) side.

- `name`: AT client name, used to identify different clients, used in
logging messages.

- `uart_handle`: An *open* `serial.Serial` object

<a id="attributes-4"></a>
#### Attributes

- `name`: AT client name, identifis the at command client (`str`).

- `uart_handle`: Client's UART handle, used to send and receive
bytes over serial interface (`serial.Serial`).

- `logger`: client's logger instance (logging.Logger)

- `last_cmd`: last sent AT command (`AtCommand`, None), default value is `None`.

- `last_status`: last AT command status (`AtCommandStatus`, None), 
default value is `None`.

- `last_response`: last AT command response (`AtCommandresponse`, None),
default value is `None`, and is set to `None` when the command times out.

- `event_lock`: A lock on events list

- `events`: A list of registered events

- `running`: A flag that is set to keep the AtCommandClient's thread running. 
Default value is clear.

- `cmd_idle`: A flag that is set when the client is not waiting for any 
response, but can be waiting for events. Default value is clear.

- `client_thread`: The thread in which the client reads incoming bytes from 
serial port, and 

<a id="methods-1"></a>
#### Methods

```python
AtCommandClient.send_command(cmd: AtCommand) -> None
```

Send given command on serial port. The function will block until the previous
command's response is received, or time out. 
`AtCommandClient.start` must be started before sending commands.


```python
AtCommandClient.add_event(event: AtEvent) -> None
```

Adds a new event to the event list. 
Can be called before calling `AtCommandClient.start()`.

```python
AtCommandClient.remove_event(event: AtEvent) -> None
```

Removes given event from event list.

```python
AtCommandClient.start() -> None
```

Start the `AtCommandClient`'s thread.

```Python
AtCommandClient.stop() -> None
```

Stops the `AtCommandClient`'s thread, any responses received 
afterwards will be ignored.

```python
AtCommandClient.on_reponse(cmd: AtCommand, 
                           status: AtCommandStatus, 
                           response: Union[AtCommandResponse, None], 
                           response_string: str) -> None
```

Called by `AtCommandClient`'s thread when a command receives a response, 
or times out. *Must* be overridden. 

```python
AtCommandClient._run() -> None
```

The main function in `AtCommandClient`'s thread. It reads lines from serial
port, and searches the received lines for matches with current command responses,
or any pending events. If a match is found, call the corresponding callback.

<a id="examples-3"></a>
#### Examples

<a id="how-to-and-examples"></a>
## How To And Examples

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading
import serial
from at_cmd_client import *
from typing import Union


got_response = threading.Event()

# AT Command Client response callback
def on_response(cmd: AtCommand, status: AtCommandStatus,
    response: Union[AtCommandResponse, None],
    response_string: Union[str, None]) -> None:

    global got_response
    got_response.set()
    string = f"Callback for Cmd {cmd.name} status: {status} "

    if response:
        string += f"Response: {response} "

    if response_string:
        string += f"Response String: {repr(response_string.strip())}"

    print(f"{string}\n")

# ready AT event callback
def is_ready(response: str, string: str) -> None:
    print(f"Ready callback. String: {repr(string.strip())}")


# OK response
ok_rsp = AtCommandResponse(
    name="OK",
    string="OK\r\n",
    matching=AtStringMatchingRule.Exact
)

# at command: AT
at_check = AtCommand(
    name="AT Check",
    cmd="AT\r\n",
    success_response=ok_rsp,
    timeout=3
)

# ready event
ready_event = AtEvent(
    name="Ready",
    string="READY\r\n",
    matching=AtStringMatchingRule.Exact,
    callback=is_ready
)

# open serial port
with serial.Serial("COM6", baudrate=115200, timeout=0.1) as ser:

    # initialize AT client
    cl = AtCommandClient('testClient', ser)

    # override AtCommandClient.on_response
    cl.on_response = on_response

    # start the client's thread
    cl.start()

    # add events
    cl.add_event(ready_event)
    cl.add_event(dt_update)

    # send command
    got_response.clear()
    cl.send_cmd(at_check)
    got_response.wait()
    print(cl)
```
