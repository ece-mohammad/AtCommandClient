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
import queue
import re
import threading
import time
from abc import ABCMeta
from typing import Callable, List, Optional, Sequence, Union

import serial
from serial.tools import list_ports


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
    """Generic AT command named string, describes the string pattern and its matching rule

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
    """AT Response, A string that is sent by AT modem/device in response to an AT command.

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

    @staticmethod
    def get_event_by_string(event_list: Sequence[object], string: str) -> Optional[object]:
        """
        Get first event from event list, where the given string matches the event string

        :param event_list: A sequence of events
        :type event_list: list, tuple
        :param string: string used to search for an event from event list
        :type string: str
        :return: an event is returned if a match with the string was found, otherwise return None
        :rtype: AtEvent or None
        """
        for event in event_list:
            assert isinstance(event, AtEvent)
            if AtString.match_string(event.string, string, event.match_type):
                return event
        return None

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


class ThreadedSerialHandler(threading.Thread):
    """
    A class for handling serial transmission in a separate thread

    Attributes

    :attr name:
    :attr huart:
    :attr logger:
    :attr tx_queue:
    :attr rx_queue:
    :attr stop_event:

    Methods

    :method start():
    :method stop():
    :method run():
    :method _send(message):
    :method receive():
    :method send_message(message):
    :method receive_message():
    :method on_thread_exception:
    """

    def __init__(self, name: str, port: str, serial_settings: dict, *args, **kwargs):

        # assert serial_settings has timeout
        assert serial_settings.get("timeout", None)

        super(ThreadedSerialHandler, self).__init__(*args, **kwargs)
        self.name: str = name
        self.logger: log.Logger = log.getLogger(f"{self.name}[{self.__class__.__name__}]")

        # serial port
        self.port: str = port
        self.serial_settings: dict = serial_settings
        self.huart: Optional[serial.Serial] = None

        # tx and rx queue
        self.tx_queue: queue.Queue[bytes] = queue.Queue()
        self.rx_queue: queue.Queue[bytes] = queue.Queue()

        # serial thread stop_event
        self.stop_event = threading.Event()

    def start(self) -> None:
        """
        start threaded serial handler

        :return: None
        :rtype: None
        """
        self.logger.debug(f"Starting {self.name}({self.__class__.__name__})")

        # open serial port
        self.huart = serial.Serial()
        self.huart.setPort(self.port)
        self.huart.apply_settings(self.serial_settings)
        self.huart.open()

        # clear serial thread stop_event
        self.stop_event.clear()

        # initialize serial thread
        super(ThreadedSerialHandler, self).start()

    def stop(self) -> None:
        """
        stop threaded serial handler

        :return: None
        :rtype: None
        """
        self.logger.debug(f"Stopping {self.name}({self.__class__.__name__})")

        # set serial thread stop_event
        self.stop_event.set()

    def _send(self, message: bytes) -> None:
        """
        send message on serial port

        :return: None
        :rtype: None
        """

        # check message length
        if len(message) == 0:
            return

        # attempt to send message
        try:
            self.huart.write(message)
        except Exception as e:
            self.logger.error(f"Exception while sending message on serial port:\n{e}")

    def _receive(self) -> bytes:
        """
        receive message from serial port

        :return: received message
        :rtype: bytes
        """

        try:
            message = self.huart.readline()
        except Exception as e:
            message = bytes()
            self.logger.error(f"Exception while reading line from serial port:\n{e}")

        return message

    def run(self) -> None:
        """
        serial handler thread runner

        :return: None
        :rtype: None
        """

        while not self.stop_event.is_set():

            # get message from tx queue
            try:
                tx_message = self.tx_queue.get(block=False)
            except queue.Empty as qe:
                tx_message = bytes()
                self.logger.debug(f"TX queue is empty")

            # send message
            self._send(tx_message)

            # receive message from serial port
            rx_message = self._receive()
            if rx_message:
                self.rx_queue.put(rx_message)

        # close serial port
        try:
            self.huart.close()
        except Exception as e:
            self.logger.error(f"Exception while trying to close serial port:\n{e}")

    def send_message(self, message: bytes) -> None:
        """
        Queues message in serial thread's tx queue to be sent

        :param message: message to be sent
        :type message: str or bytes
        :return: None
        :rtype: None
        """

        self.tx_queue.put(message)

    def receive_message(self) -> bytes:
        """
        Receive message from serial thread rx queue

        :return: message from rx queue
        :rtype: bytes
        """

        try:
            rx_message = self.rx_queue.get(block=False)
        except queue.Empty as qe:
            rx_message = bytes()
            self.logger.debug("RX queue is empty")

        return rx_message

    def on_thread_exception(self, exception: Exception) -> None:
        """
        callback to notify parent thread of exceptions caught in Thread.run

        :note: will NOT be called for un handled exceptions

        :param exception: caught exception
        :type exception: Exception
        :return: None
        :rtype: None
        """

        self.logger.error(f"Caught exception: {exception}")


class AtCommandClient(object):
    """At Command Client class, used to send AT commands and receive their responses

    Attributes

    :attr name: client name, identifies it and is used in logging
    :attr logger: client's logger instance
    :attr serial_port: serial port used to send and receive At commands
    :attr serial_settings: serial port settings (baudrate, timeout, data bits, parity, stop bits, etc)
    :attr serial_handler: serial port handler thread
    :attr last_cmd: last command sent by the client
    :attr last_status: last command status
    :attr last_response: last response received
    :attr client_not_busy: a flag that indicates if the client is waiting for
        a response or not (set == not waiting for response, clear == waiting for response)
    :attr events: list of registered events
    :attr lock: a lock on `self.events` to prevent access from multiple threads at the same time
    :attr client_thread: a thread to stop the clients `AtCommandClient.process_response`
        function, that handles responses and events
    :attr stop_event: a flag that indicates if the client is stop_event or not,
        resetting the flag terminates the client's thread

    Methods

    :method start: start AtCommandClient's thread
    :method stop: stop AtCommandClient's thread
    :method process_response: handles AT commands responses and events, and calls associated callbacks whn needed
    :method send_cmd: send AT command
    :method add_event: add event to current event list
    :method remove_event: remove an event from current event list
    :method on_response: a callback that is called when a command response is received, must be overridden
    """

    def __init__(self, name: str, serial_port: str, serial_settings: dict) -> None:
        # check serial port is available
        assert serial_port in [port.name for port in list_ports.comports()]

        # assert timeout value is present and not zero
        assert serial_settings.get("timeout", 0)

        self.name: str = name
        self.logger: log.Logger = log.getLogger(f"{self.name}[{self.__class__.__name__}]")

        # serial port handler
        self.serial_port: str = serial_port
        self.serial_settings: dict = serial_settings
        self.serial_handler: Optional[ThreadedSerialHandler] = None

        # lst AT command, status, response object and received response string
        self.last_cmd: Optional[AtCommand] = None
        self.last_response: Optional[AtCommandResponse] = None
        self.last_status: Optional[AtCommandStatus] = None

        # client busy event
        self.client_not_busy: threading.Event = threading.Event()

        # AT events list
        self.events: List[AtEvent] = list()

        # client lock
        self.lock: threading.RLock = threading.RLock()

        # client's thread
        self.client_thread: Optional[threading.Thread] = None
        self.stop_event: threading.Event = threading.Event()

        # lock acquire & release count
        self.lock_acquired_count: int = 0
        self.lock_released_count: int = 0

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

    def start(self) -> None:
        """
        Starts the client thread

        :return: None
        :rtype: None
        """

        self.logger.info(f"Starting {self.name}")

        # lock acquire & release count
        self.lock_acquired_count: int = 0
        self.lock_released_count: int = 0

        # reset last AT command, response and response buffer
        self.last_cmd: Optional[AtCommand] = None
        self.last_response: Optional[AtCommandResponse] = None
        self.last_status: Optional[AtCommandStatus] = None

        # set client not busy flag
        self.client_not_busy.set()

        # initialize client thread
        self.client_thread = threading.Thread(
            name=f"{self.name}[ClientThread]",
            target=self.process_response,
            daemon=False,
        )

        # initialize serial handler
        self.serial_handler = ThreadedSerialHandler(
            name=f"{self.name}(SerialHandler)",
            port=self.serial_port,
            serial_settings=self.serial_settings
        )

        # clear client thread stop event & start client thread
        self.stop_event.clear()
        self.client_thread.start()

        # start serial handler thread
        self.serial_handler.start()

    def _close_client_thread(self) -> None:
        """
        Close client thread

        :return: None
        :rtype: None
        """

        self.logger.debug(f"Closing client thread")

        if self.client_thread is None:
            return

        # set stop event
        self.stop_event.set()

        try:
            self.client_thread.join(1)
        except Exception as e:
            self.logger.error(f"Exception while waiting for {self.name}'ss client thread to close:\n {e}")

        if self.client_thread.is_alive():
            self.logger.critical(f"Failed to close {self.name}'s client thread")

    def _close_serial_handler_thread(self) -> None:
        """
        Close serial handler thread

        :return: None
        :rtype: None
        """

        self.logger.debug(f"Closing serial handler thread")

        if self.serial_handler is None:
            return

        self.serial_handler.stop()

        try:
            self.serial_handler.join(1)
        except Exception as e:
            self.logger.error(f"Exception while waiting for {self.name}'ss client thread to close:\n {e}")

        if self.serial_handler.is_alive():
            self.logger.critical(f"Failed to close {self.name}'s client thread")

    def stop(self) -> None:
        """
        Stop the AtCommandClient's stop_event thread

        :return: None
        :rtype: None
        """

        self.logger.info(f"Stopping {self.name}")

        # stop serial handler thread
        self._close_serial_handler_thread()

        # stop client thread
        self._close_client_thread()

        self.logger.info(f"Lock acquired count: {self.lock_acquired_count}")
        self.logger.info(f"Lock released count: {self.lock_released_count}")

    def process_response(self) -> None:
        """
        Handles receiving AT commands responses and events, and calling their callbacks when needed.

        :note: runs in its own thread.

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

        self.logger.info(f"Starting process_response")

        # while client is stop_event
        while not self.stop_event.is_set():

            self.logger.info("Attempting to acquire lock")

            # get lock
            with self.lock:

                self.lock_acquired_count += 1
                self.logger.info("Lock acquired")

                # read message from serial handler
                received_line = self.serial_handler.receive_message()

                # decode read message
                try:
                    received_line = received_line.decode("ascii")
                except Exception as e:
                    self.logger.error(f"Exception while decoding received line from urat:\n{e}\n{received_line}")
                    received_line = b""

                response_buffer += received_line

                # look for an event that matches response buffer
                event = AtEvent.get_event_by_string(self.events, response_buffer)
                if event is not None and isinstance(event, AtEvent):

                    # call event callback
                    event.callback(event.string, response_buffer)

                    # remove event if it's a onetime event
                    if event.event_type == AtEventType.OneTime:
                        self.events.remove(event)

                    # clear response buffer
                    response_buffer = str()

                # ISSUE #12
                # when closing client from pySIM800, the client thread never joins
                # and client_thread.is_alive always return true event though
                # stop_event event is cleared
                # checking command is not None prevents raising an exception
                # when calculating timeout time of command if command was None
                # (start then stop without sending any commands)
                # if no command response is pending, continue
                if self.last_cmd is None or self.client_not_busy.is_set():
                    time.sleep(0.5)

                    self.lock_released_count += 1
                    self.logger.info("Lock released")

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
                    self.last_cmd = None
                    self.client_not_busy.set()

                    self.lock_released_count += 1
                    self.logger.info("Lock released")

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

                # reset response buffer & clear client_not_busy
                if match:
                    response_buffer = str()
                    self.last_cmd = None
                    self.last_status = None
                    self.last_response = None
                    self.client_not_busy.set()

            self.lock_released_count += 1
            self.logger.info("Lock released")

            time.sleep(0.5)

        self.logger.info(f"Returning from process_response")

    def send_cmd(self, cmd: AtCommand) -> None:
        """
        Send command on UART, blocks until the current command's response is received before sending a new command.

        :param cmd: Command to be sent to GSM module over UART
        :type cmd: AtCommand
        :return: None
        :rtype: None
        """

        self.logger.info("Attempting to acquire lock")

        # acquire lock
        with self.lock:
            self.lock_acquired_count += 1
            self.logger.info("Lock acquired")

            self.logger.info("Waiting client_not_busy")

            # wait until client is not busy
            self.client_not_busy.wait()

            self.logger.info("Done waiting client_not_busy")

            self.logger.debug(f"Sending cmd {cmd.name}: {repr(cmd.cmd)}")

            # set last command = cmd
            self.last_cmd = cmd

            # clear last status
            self.last_status = None

            # clear last response
            self.last_response = None

            # send command on serial port
            if isinstance(cmd.cmd, str):
                cmd.cmd = bytes(cmd.cmd, "ascii")

            self.serial_handler.send_message(cmd.cmd)

            # command send time
            cmd.send_time = time.time()

            # clear client_not_busy
            self.client_not_busy.clear()

        self.lock_released_count += 1
        self.logger.info(f"Lock released")

    def add_event(self, event: AtEvent) -> None:
        """
        Adds a new event to event list. Blocks until the event is added.

        :param event: At event to add
        :type event: AtEvent
        :return: None
        :rtype: None
        """

        self.logger.info("Attempting to acquire lock")

        # acquire lock
        with self.lock:

            self.lock_acquired_count += 1
            self.logger.info("Lock acquired")

            if event not in self.events:
                self.events.append(event)

        self.lock_released_count += 1
        self.logger.info("Lock released")

    def remove_event(self, event: AtEvent) -> None:
        """
        Removes the given event from event list. Blocks until the event is removed

        :param event: event to remove from event list
        :type event: AtEvent
        :return: None
        :rtype: None
        """

        self.logger.info("Attempting to acquire lock")

        # get lock
        with self.lock:

            self.lock_acquired_count += 1
            self.logger.info("Lock acquired")

            try:
                self.events.remove(event)
            except Exception as e:
                self.logger.error(f"Can't remove event {event.name} from event list")

        self.lock_released_count += 1
        self.logger.info("Lock released")

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

    log.basicConfig(
        stream=sys.stdout,
        level=log.INFO,
        # format="%(levelname)s:%(name)s:%(threadName)s:%(funcName)s:%(lineno)d %(message)s"
        format="%(levelname)s:%(threadName)s:%(funcName)s:%(lineno)d %(message)s"
    )

    SERIAL_PORT: str = "COM6"
    SERIAL_SETTINGS: dict = {
        "baudrate": 115200,
        "timeout": 0.1
    }


    def is_ready(response: str, string: str) -> None:
        log.info(f"Ready event callback. String: {repr(string.strip())}")


    def time_update(response: str, string: str) -> None:
        log.info(f"Date Time Update Event Callback. String: {repr(string.strip())}")


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

    # time event
    dt_update = AtEvent(
        name="Date Time Update",
        string="\\+CCLK:\\s*.*\r\n",
        event_type=AtEventType.Reoccurring,
        matching=AtStringMatchingRule.Regex,
        callback=time_update
    )

    # # print responses
    # log.debug(ok_rsp)
    # log.debug(dt_rsp)
    # log.debug(cme_error)
    # log.debug(cms_error)
    # log.debug("-----------------------------")
    #
    # # log.debug commands
    # log.debug(at_check)
    # log.debug("-----------------------------")
    #
    # log.debug(at_cme)
    # log.debug("-----------------------------")
    #
    # log.debug(at_cms)
    # log.debug("-----------------------------")
    #
    # log.debug(at_dt)
    # log.debug("-----------------------------")
    #
    # log.debug(at_timeout)
    # log.debug("-----------------------------")

    got_response = threading.Event()


    def on_response(cmd: AtCommand,
                    status: AtCommandStatus,
                    response: Optional[AtCommandResponse],
                    response_string: Optional[str]
                    ) -> None:

        global got_response

        got_response.set()

        if status == AtCommandStatus.Timeout:
            log.error(f"Response for cmd: {repr(cmd.cmd)} timed out")

        elif status == AtCommandStatus.Error:
            log.error(f"Error response for cmd: {repr(cmd.cmd)}")

        else:
            log.debug(f"Callback for Cmd {cmd.name} status: {status}")

        if response:
            log.debug(f"Response: {repr(response.string)} matching rule: {response.match_type.name}")

        if response_string:
            log.debug(f"Response String: {repr(response_string)}")


    def on_event(event: AtEvent, string: str, response: str) -> None:
        log.debug(f"Received event: {event.name}, string: {string.strip()}, response: {response.strip()}")


    # initialize client
    cl = AtCommandClient(
        name="testClient",
        serial_port=SERIAL_PORT,
        serial_settings=SERIAL_SETTINGS
    )

    cl.on_response = on_response

    cl.add_event(ready_event)
    cl.add_event(dt_update)

    cl.start()
    time.sleep(1)
    cl.stop()

    # time.sleep(1)
    # cl.stop()
    # sys.exit(0)

    time.sleep(1)
    cl.start()
    time.sleep(1)
    cl.stop()

    # sys.exit(0)

    # send commands
    cl.start()
    got_response.clear()
    cl.send_cmd(at_check)
    got_response.wait()
    # log.debug(cl)
    log.debug("-----------------------------")

    # cl.stop()
    # sys.exit(0)

    got_response.clear()
    cl.send_cmd(at_cme)
    got_response.wait()
    # log.debug(cl)
    log.debug("-----------------------------")

    got_response.clear()
    cl.send_cmd(at_cms)
    got_response.wait()
    # log.debug(cl)
    log.debug("-----------------------------")

    got_response.clear()
    cl.send_cmd(at_multiline)
    got_response.wait()
    # log.debug(cl)
    log.debug("-----------------------------")

    got_response.clear()
    cl.send_cmd(at_dt)
    got_response.wait()
    # log.debug(cl)
    log.debug("-----------------------------")

    got_response.clear()
    cl.send_cmd(at_timeout)
    got_response.wait()
    # log.debug(cl)
    log.debug("-----------------------------")

    got_response.clear()
    cl.send_cmd(at_prompt)
    got_response.wait()
    # log.debug(cl)
    log.debug("-----------------------------")

    got_response.clear()
    cl.send_cmd(at_prompt_err)
    got_response.wait()
    # log.debug(cl)
    log.debug("-----------------------------")

    # send events & close
    log.critical("Waiting for events. Press q to close. ")
    close = ""
    while close != 'q':
        close = input().strip().lower()
    cl.stop()
