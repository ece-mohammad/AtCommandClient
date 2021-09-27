#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# -----------------------------------------------------------------------------
#
# at_cmd_client is a python package that provides classes to send
# and receive AT commands over a serial port (UART), to control a device
# that supports AT commands, like GSM modules (SIM800, a9G, etc),
# ESP32 and its variants, Bluetooth modules, and others.
#
# The package provides named strings for commands and responses,
# response string detection using regex patterns, asynchronous
# response handling and unsolicited response handling.
#
# Classes:
#
# AtCommandClient(name, uart_handle)
#     An AT command client, that transmits and receives AT commands on a serial
#     interface.
#
# AtCommand(name, cmd, success_response, error_responses, timeout)
#     A class that wraps AT commands with its expected success and error
#     responses. Supports regex pattern matching.
#
# AtCommandResponse(name, string, matching)
#     A class for AT commands' responses.
#
# AtEvent(name, string, callback, event_type, matching)
#   A class for unsolicited AT responses.
#
# Licenced under MIT licence. Check LICENCE.txt
#
# -----------------------------------------------------------------------------


import enum
import logging as log
import re
import threading
import time
from abc import ABCMeta
from typing import Callable, List, Union, Optional

import serial


@enum.unique
class AtCommandStatus(enum.Enum):
    """AT Command Status, an Enum used to indicates the status of the response of an AT command

    AtCommandStatus.Success: AT command was sent and a success response was received within command timeout
    AtCommandStatus.Error: AT command was sent and an error response was received within command timeout
    AtCommandStatus.Timeout: AT command was sent but no response was received within command timeout
    """

    Success = enum.auto()
    Error = enum.auto()
    Timeout = enum.auto()


@enum.unique
class AtStringMatchingRule(enum.Enum):
    """AT String Match Type, an Enum used to define how to search for pattern string within another string

    AtStringMatchingRule.Regex: use the pattern string as a regex expression
    AtStringMatchingRule.Exact: use the pattern string as is
    """

    Regex = enum.auto()
    Exact = enum.auto()


@enum.unique
class AtEventType(enum.Enum):
    """At Event Type, an Enum that describes AT event recurrence

    AtEventType.OneTime: An event that occurs only one time
    AtEventType.Reoccurring: An event that repeats infinitely
    """

    OneTime = enum.auto()
    Reoccurring = enum.auto()


class AtString(metaclass=ABCMeta):
    """Generic AT command named string, describes the string pattern and its
    matching rule

    :attr name: String name, used to identify the string.
                Can be an empty string, though not recommended
    :attr string: String pattern
    :attr match_type: one of AtStringMatchingRule

    :method match_string(pattern: str, string: str, match_type: AtStringMatchingRule) -> str:
    """

    def __init__(self, name: str,
                 string: str,
                 matching: AtStringMatchingRule = AtStringMatchingRule.Regex) -> None:
        self.name = name
        self.string = string
        self.match_type = matching

    def __str__(self) -> str:
        return f"AT String {self.name} string: {self.string.strip()}"

    @staticmethod
    def match_string(pattern: str, string: str,
                     match_type: AtStringMatchingRule) -> str:
        """
        Search for and return an occurrence of `pattern` within `string`,
        according to `match_type`. When AtStringMatchingRule.Regex is used,
        the first match found is returned.
        :param pattern: string pattern to search for (needle)
        :type pattern: str
        :param string: string to search into (hay stack)
        :type string: str
        :param match_type: How to look for `pattern` in `string`.
        AtStringMatchingRule.Exact: `string` is searched for `pattern` i.e
        `pattern` is a sub-string o `string`.
        AtStringMatchingRule.Regex: `pattern` is used as a regular expression
        pattern.
        :type match_type: AtStringMatchingRule
        :return: matching string pattern, or an empty string if `pattern` is not
        in `string`
        :rtype: str
        """
        # check if string matching rule == regex
        if match_type == AtStringMatchingRule.Regex:

            # check if there is a string that matches pattern regex
            # string in the given string
            match = re.findall(pattern, string, re.DOTALL)
            if match:
                return match[0]
            else:
                return ""

        else:
            # check if pattern string exists within given string
            if pattern in string:
                return pattern

        return ""


class AtCommandResponse(AtString):
    """AT Response, A string that is sent by AT modem/device in response
    to an AT command.

    :attr name: Response name, used to identify the response
    :attr string: Response string
    :attr match_type: How to search for response in the received response string
    """

    def __str__(self) -> str:
        return f"AT Response {self.name} string: {self.string.strip()}"


class AtEvent(AtString):
    """AT Event, a class for un-solicited AT responses

    :attr name: event name, used to identify the event
    :attr string: event string
    :attr callback: event callback, called with the event string and
    the received response string as parameters
    :attr match_type: How to search for event string in the received response string
    :attr event_type: Event type, AtEventType.OneTime or AtEventType.Reoccurring
    """

    def __init__(self, name: str,
                 string: str,
                 callback: Callable[[str, str], None],
                 event_type: AtEventType = AtEventType.OneTime,
                 matching: AtStringMatchingRule = AtStringMatchingRule.Regex) -> None:
        super(AtEvent, self).__init__(
            name=name,
            string=string,
            matching=matching
        )

        self.event_type = event_type
        self.callback = callback

    def __str__(self) -> str:
        return f"AT Event {self.name}\n" \
               f"string: {self.string.strip()}\n" \
               f"typeL {self.event_type}\n" \
               f"callback: {self.callback.__name__}\n"


class AtCommand(object):
    """AT Command class, describes an AT command and its expected responses

    :attr name: AT command name, used to identify it
    :attr cmd: AT command string
    :attr timeout: time to wait after sending the command before time out
    :attr success_response: a AtCommandResponse for success response
    :attr error_response: a list of AtCommandResponse error responses
    """

    def __init__(self, name: str,
                 cmd: Union[str, bytes],
                 success_response: Optional[AtCommandResponse],
                 error_response: Optional[List[AtCommandResponse]] = None,
                 timeout: float = 0) -> None:
        self.name = name
        self.cmd = cmd
        self.send_time: float = 0
        self.timeout: float = timeout
        self.success_response = success_response
        self.error_response = error_response

    def __str__(self) -> str:
        string = f"AT Command {self.name}:\n" \
                 f"string: {self.cmd.strip()}\n" \
                 f"timeout: {self.timeout}\n" \
                 f"success response: {self.success_response}"

        if self.error_response:
            string += "\nError responses:\n"
            for rsp in self.error_response:
                string += f"{rsp}\n"

            string = string.strip()

            string = string.strip()

        return string


class AtCommandClient(object):
    """At Command Client class, used to send AT commands and receive their
    responses

    Attributes

    :attr name: client name, identifies it and is used in logging
    :attr huart: serial port used to send and receive At commands
    :attr logger: client's logger instance
    :attr last_cmd: last command sent by the client
    :attr last_status: last command status
    :attr last_response: last response received
    :attr events: list of registered events
    :attr event_lock: a lock on `self.events` to prevent access from multiple
    threads at the same time
    :attr running: a flag that indicates if the client is running or not,
    resetting the flag terminates the client's thread
    :attr client_ready: a flag that indicates if the client is waiting for
    a response
    :attr client_thread: a thread to run the clients `AtCommandClient._run`
    function, that handles responses and events

    Methods

    :method send_cmd: send AT command
    :method add_event: add event to current event list
    :method remove_event: remove an event from current event list
    :method start: start AtCommandClient's thread
    :method stop: stop AtCommandClient's thread
    :method on_response: a callback that is called when a command response is
    received, must be overridden
    :method _run: handles AT commands responses and events, and calls
    associated callbacks whn needed
    """

    def __init__(self, name: str, uart_handle: serial.Serial) -> None:
        self.name = name
        self.huart = uart_handle
        self.logger = log.getLogger(f"{self.name}({self.__class__.__name__})")
        self.last_cmd: Optional[AtCommand] = None
        self.last_response: Optional[AtCommandResponse] = None
        self.last_status: Optional[AtCommandStatus] = None
        self.events: List[AtEvent] = list()
        self.client_thread = threading.Thread(target=self._run, daemon=False)
        self.event_lock = threading.RLock()
        self.running = threading.Event()
        self.client_ready = threading.Event()

        # set client ready flag
        self.client_ready.set()

    def __str__(self) -> str:
        string = f"Module: {self.name}\n"

        if self.last_cmd:
            string += f"last command: {self.last_cmd.name} " \
                      f"String: {self.last_cmd.cmd.strip()}\n" \
                      f"Status: {self.last_status}\n"

        if self.last_response:
            string += f"last response: {self.last_response.name} " \
                      f"string: {self.last_response.string.strip()}\n"

        return string

    def send_cmd(self, cmd: AtCommand) -> None:
        """
        Send command on UART, blocks until the current command's response
        is received before sending a new command
        :param cmd: Command to be sent to GSM module over UART
        :type cmd: AtCommand
        :return: None
        :rtype: None
        """

        # check if client is client_ready
        self.client_ready.wait()

        self.logger.debug(f"Sending cmd {cmd.name}: {cmd.cmd.strip()}")

        # set last command = cmd
        self.last_cmd = cmd

        # clear last response
        self.last_response = None

        # clear last response
        self.last_response = None

        # send command on serial
        if isinstance(cmd.cmd, str):
            self.huart.write(bytes(cmd.cmd, "ascii"))
        else:
            self.huart.write(cmd.cmd)

        # command send time
        cmd.send_time = time.time()

        # clear client_ready
        self.client_ready.clear()

    def add_event(self, event: AtEvent) -> None:
        """
        Adds a new event to event list. Blocks until the event is added.
        :param event: At event to add
        :type event: AtEvent
        :return: None
        :rtype: None
        """
        with self.event_lock:
            self.events.append(event)

    def remove_event(self, event: AtEvent) -> None:
        """
        Removes the given event from event list. Blocks until the event is
        removed
        :param event: event to remove from event list
        :type event: AtEvent
        :return: None
        :rtype: None
        """
        with self.event_lock:
            try:
                self.events.remove(event)
            except ValueError as value_err:
                self.logger.error(f"Can remove event {event} from event list")

    def start(self) -> None:
        """
        Starts the client thread
        :return: None
        :rtype: None
        """
        self.running.set()
        self.client_ready.set()
        self.client_thread.start()

    def stop(self) -> None:
        """
        Stop the AtCommandClient's running thread
        :return: None
        :rtype: None
        """
        self.running.clear()
        self.client_ready.clear()

        while self.client_thread.is_alive():
            time.sleep(0.1)

    def _run(self) -> None:
        """
        Handles receiving AT commands responses and events, and calling their
        callbacks when needed. Runs in its own thread.

        Function breakdown:

        1. if is_running flag is reset, return, else:

        2. read line from serial port and append it to response_buffer

        3. get event lock

        4. loop over events in event list

        5. if event string was found in response_buffer:
            - call event's callback
            - clear response_buffer
            - if event is a one time event, remove it from event list
            - exit loop [4]
            - end if [5]

        7. if response_pending flag is reset, go to step [13], else:

        8. if current time > command timeout:
            - call response_callback with timeout status
            - clear response_pending flag
            - go to step [13]
            - end if [8]

        9. if command's success response was found in response_buffer:
            - call response_callback with success status
            - end if [9]

        10. loop over command's error responses

        11. If error string was found in response_buffer:
            - call response_callback with error status
            - exit loop [10]
            - end if [11]

        12. If a match as found with a success or error response
            - clear response_pending flag
            - clear response_buffer
            - end if [12]

        13. sleep for 100 milliseconds (0.1 seconds)

        14. go to step [1]

        :return: None
        :rtype: None
        """
        # response buffer
        response_buffer: str = str()

        # while client is running
        while self.running.is_set():

            # read line from uart
            response_buffer += self.huart.readline().decode("ascii")

            # get events lock
            with self.event_lock:

                # loop over a copy of added events
                for event in self.events[:]:
                    match = AtString.match_string(
                        event.string,
                        response_buffer,
                        event.match_type
                    )

                    # check for an event match
                    if match:
                        event.callback(event.string, match)
                        response_buffer = str()

                        # remove one-time events
                        if event.event_type == AtEventType.OneTime:
                            self.events.remove(event)

                        break

            # if no command response is pending, continue
            if self.client_ready.is_set():
                continue

            # calculate command timeout
            timeout_time: float = self.last_cmd.send_time + self.last_cmd.timeout

            # check if command timed out
            if time.time() > timeout_time:
                # command response timed out
                self.last_status = AtCommandStatus.Timeout
                self.last_response = None
                self.on_response(
                    self.last_cmd,
                    self.last_status,
                    self.last_response,
                    None
                )

                self.client_ready.set()
                continue

            # check success response string was found in response string
            match = AtString.match_string(
                self.last_cmd.success_response.string,
                response_buffer,
                self.last_cmd.success_response.match_type
            )

            # check if received line matches success response
            if match:
                self.last_response = self.last_cmd.success_response
                self.last_status = AtCommandStatus.Success
                self.on_response(
                    self.last_cmd,
                    self.last_status,
                    self.last_response,
                    match
                )

            # check on of error responses string was found in response string
            elif self.last_cmd.error_response:
                for err in self.last_cmd.error_response:
                    match = AtString.match_string(
                        err.string,
                        response_buffer,
                        err.match_type
                    )

                    if match:
                        self.last_response = err
                        self.last_status = AtCommandStatus.Error
                        self.on_response(
                            self.last_cmd,
                            self.last_status,
                            self.last_response,
                            match
                        )
                        break

            # reset response buffer & clear client_ready
            if match:
                response_buffer = str()
                self.client_ready.set()

            time.sleep(0.1)

    def on_response(self, cmd: AtCommand,
                    status: AtCommandStatus,
                    response: Optional[AtCommandResponse],
                    response_string: Optional[str]
                    ) -> None:
        """
        Response callback, called when a command's response is received, or
        no response is received within command's timeout. Must be overridden.

        :param cmd: command for which this callback is called
        :type cmd: AtCommand
        :param status: Command status
            AtCommandStatus.Success: command's success response was received
            AtCommandStatus.Error: command's error response was received
            AtCommandStatus.Timeout: no response was received before timeout
        :type status: AtCommandStatus
        :param response: Received command response (error or success), or None
        if the command timed out
        :type response: Optional[AtCommandResponse]
        :param response_string: the response buffer, containing the command's
        response string (success or error), or None if the command timed out
        :type response_string: Optional[str]
        :return: None
        :rtype: None
        """
        pass


if __name__ == '__main__':
    import sys

    log.basicConfig(stream=sys.stdout)


    def is_ready(response: str, string: str) -> None:
        print(f"Ready callback. String: {repr(string.strip())}")


    def time_update(response: str, string: str) -> None:
        print(f"Device Date Time Update Callback. String: {repr(string.strip())}")


    COM_PORT = "COM6"

    # ok response
    ok_rsp = AtCommandResponse(
        name="OK",
        string="OK\r\n",
        matching=AtStringMatchingRule.Exact
    )

    # multiline command response
    multiline_response = AtCommandResponse(
        name="Multiline Response",
        string="\\+ML.*OK\r\n",
        matching=AtStringMatchingRule.Regex
    )

    # date send_time response
    dt_rsp = AtCommandResponse(
        name="Date Time",
        string="\\+CCLK=.*OK\r\n",
        matching=AtStringMatchingRule.Regex
    )

    # cme error
    cme_error = AtCommandResponse(
        name="CME Error",
        string="\\+CME ERROR:\\s*\\d+\r\n",
        matching=AtStringMatchingRule.Regex
    )

    # cms error
    cms_error = AtCommandResponse(
        name="CMS Error",
        string="\\+CMS ERROR:\\s*\\d+\r\n",
        matching=AtStringMatchingRule.Regex
    )

    # prompt response OK
    prompt_rsp = AtCommandResponse(
        name="Prompt Response",
        string=">",
        matching=AtStringMatchingRule.Exact
    )

    # prompt error
    prompt_error = AtCommandResponse(
        name="Prompt Error",
        string="ERROR\r\n",
        matching=AtStringMatchingRule.Exact
    )

    # send error
    send_error_rsp = AtCommandResponse(
        name="Send Error",
        string="SEND ERROR\r\n",
        matching=AtStringMatchingRule.Exact
    )

    # send fail
    send_fail_rsp = AtCommandResponse(
        name="Send Fail",
        string="SEND FAIL\r\n",
        matching=AtStringMatchingRule.Exact
    )

    # at command: AT
    at_check = AtCommand(
        name="AT Check",
        cmd="AT\r\n",
        success_response=ok_rsp,
        timeout=3
    )

    # cme error command
    at_cme = AtCommand(
        name="AT CME Error",
        cmd="AT+ERROR=CME\r\n",
        success_response=ok_rsp,
        error_response=[cme_error, cms_error],
        timeout=3
    )

    # cms error command
    at_cms = AtCommand(
        name="AT CMS Error",
        cmd="AT+ERROR=CMS\r\n",
        success_response=ok_rsp,
        error_response=[cme_error, cms_error],
        timeout=3
    )

    # multiline command
    at_multiline = AtCommand(
        name="AT Multiline",
        cmd="AT+ML?\r\n",
        success_response=multiline_response,
        timeout=3
    )

    # date-time command
    at_dt = AtCommand(
        name="AT Date Time",
        cmd="AT+CCLK?\r\n",
        success_response=dt_rsp,
        timeout=3
    )

    # timeout
    at_timeout = AtCommand(
        name="AT Timeout",
        cmd="AT+TIMEOUT\r\n",
        success_response=ok_rsp,
        timeout=3
    )

    # prompt command
    at_prompt = AtCommand(
        name="Prompt",
        cmd="AT+CIPSEND=10\r\n",
        success_response=prompt_rsp,
        error_response=[send_fail_rsp, send_error_rsp],
        timeout=3
    )

    # prompt error command
    at_prompt_err = AtCommand(
        name="Prompt Error",
        cmd="AT+CIPSEND=0\r\n",
        success_response=prompt_rsp,
        error_response=[send_fail_rsp, send_error_rsp],
        timeout=3
    )

    # ready event
    ready_event = AtEvent(
        name="Ready",
        string="READY\r\n",
        matching=AtStringMatchingRule.Exact,
        callback=is_ready
    )

    # ready event
    dt_update = AtEvent(
        name="Date Time Update",
        string="\\+CCLK:\\s*.*\r\n",
        event_type=AtEventType.Reoccurring,
        matching=AtStringMatchingRule.Regex,
        callback=time_update
    )

    # print responses
    print(ok_rsp)
    print(dt_rsp)
    print(cme_error)
    print(cms_error)
    print("-----------------------------")

    # print commands
    print(at_check)
    print("-----------------------------")

    print(at_cme)
    print("-----------------------------")

    print(at_cms)
    print("-----------------------------")

    print(at_dt)
    print("-----------------------------")

    print(at_timeout)
    print("-----------------------------")

    got_response = threading.Event()


    def on_response(
        cmd: AtCommand,
        status: AtCommandStatus,
        response: Optional[AtCommandResponse],
        response_string: Optional[str]
    ) -> None:
        global got_response
        got_response.set()
        string = f"Callback for Cmd {cmd.name} status: {status} "

        if response:
            string += f"Response: {response} "

        if response_string:
            string += f"Response String: {repr(response_string.strip())}"

        print(f"{string}\n")


    def on_event(event: AtEvent, string: str, response: str) -> None:
        print(f"Received event: {event.name}, string: {string.strip()}, response: {response.strip()}")


    with serial.Serial("COM6", baudrate=115200, timeout=0.1) as ser:
        cl = AtCommandClient('testClient', ser)
        cl.on_response = on_response
        cl.start()

        cl.add_event(ready_event)
        cl.add_event(dt_update)

        # send commands
        got_response.clear()
        cl.send_cmd(at_check)
        got_response.wait()
        print(cl)
        print("-----------------------------")

        got_response.clear()
        cl.send_cmd(at_cme)
        got_response.wait()
        print(cl)
        print("-----------------------------")

        got_response.clear()
        cl.send_cmd(at_cms)
        got_response.wait()
        print(cl)
        print("-----------------------------")

        got_response.clear()
        cl.send_cmd(at_multiline)
        got_response.wait()
        print(cl)
        print("-----------------------------")

        got_response.clear()
        cl.send_cmd(at_dt)
        got_response.wait()
        print(cl)
        print("-----------------------------")

        got_response.clear()
        cl.send_cmd(at_timeout)
        got_response.wait()
        print(cl)
        print("-----------------------------")

        got_response.clear()
        cl.send_cmd(at_prompt)
        got_response.wait()
        print(cl)
        print("-----------------------------")

        got_response.clear()
        cl.send_cmd(at_prompt_err)
        got_response.wait()
        print(cl)
        print("-----------------------------")

        # send events & close
        print("Waiting for events. Press q to close. ")
        close = ""
        while close != 'q':
            close = input().strip().lower()
        cl.stop()
