#!/usr/bin/env python3
# -*- coding; utf-8 -*-


import enum
import logging as log
import queue
import re
import threading
import time
from typing import Union, List

import serial


@enum.unique
class AtCommandStatus(enum.Enum):
    """AT Command Status"""

    Success = enum.auto()
    Error = enum.auto()
    Timeout = enum.auto()


@enum.unique
class AtStringMatchingRule(enum.Enum):
    """AT String Match Type"""

    Regex = enum.auto()
    Exact = enum.auto()


@enum.unique
class AtEventType(enum.Enum):
    """At Event Type"""
    OneTime = enum.auto()
    Reoccurring = enum.auto()


@enum.unique
class AtClientState(enum.Enum):
    """At Client State"""

    Idle = enum.auto()
    Busy = enum.auto()


class AtString(object):
    """At Command Response"""

    def __init__(self, name: str, string: str, matching: AtStringMatchingRule = AtStringMatchingRule.Regex) -> None:
        self.name = name
        self.string = string
        self.match_type = matching

    def __str__(self) -> str:
        return f"AT String {self.name} string: {self.string.strip()}"


class AtCommandResponse(AtString):
    def __str__(self) -> str:
        return f"AT Response {self.name} string: {self.string.strip()}"


class AtEvent(object):
    """AT Event"""

    def __init__(self, name: str,
                 string: str,
                 callback: callable,
                 event_type: AtEventType = AtEventType.OneTime,
                 matching: AtStringMatchingRule = AtStringMatchingRule.Regex) -> None:
        self.name = name
        self.string = string
        self.match_type = matching
        self.event_type = event_type
        self.callback = callback

    def __str__(self) -> str:
        return f"AT Event {self.name}\n" \
               f"string: {self.string.strip()}\n" \
               f"typeL {self.event_type}\n" \
               f"callback: {self.callback.__name__}\n"


class AtCommand(object):
    """AT Command"""

    def __init__(self, name: str,
                 cmd: str,
                 success_response: Union[AtCommandResponse, None],
                 error_response: Union[List[AtCommandResponse], None] = None,
                 other_response: Union[List[AtCommandResponse], None] = None,
                 timeout: float = 0) -> None:
        self.name = name
        self.cmd = cmd
        self.send_time: float = 0
        self.timeout: float = timeout
        self.success_response = success_response
        self.error_response = error_response
        self.other_response = other_response

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

        if self.other_response:
            string += "\nOther responses:\n"
            for rsp in self.other_response:
                string += f"{rsp}\n"

            string = string.strip()

        return string


class AtCommandClient(object):
    """GSM module base class"""

    def __init__(self, name: str, uart_handle: serial.Serial) -> None:
        self.name = name
        self.huart = uart_handle
        self.logger = log.getLogger(self.__class__.__name__)
        self.response_buffer: queue.Queue = queue.Queue(10)
        self.last_cmd: Union[AtCommand, None] = None
        self.last_response: Union[AtCommandResponse, None] = None
        self.event_lock = threading.RLock()
        self.events: List[AtEvent] = list()
        self.running = threading.Event()
        self.cmd_idle = threading.Event()
        self.client_thread = threading.Thread(target=self._run, daemon=False)

        # set cmd_idle flag
        self.cmd_idle.set()

    def __str__(self) -> str:
        string = f"Module: {self.name}\n"

        if self.last_cmd:
            string += f"last command: {self.last_cmd.name} string: {self.last_cmd.cmd.strip()}\n"

        if self.last_response:
            string += f"last response: {self.last_response.name} string: {self.last_response.string.strip()}\n"

        return string

    def send_cmd(self, cmd: AtCommand) -> None:
        """
        Send command on UART
        :param cmd: Command to be sent to GSM module over UART
        :type cmd: AtCommand
        :return: None
        :rtype: None
        """

        # check if client is cmd_idle
        self.cmd_idle.wait()

        self.logger.debug(f"Sending cmd {cmd.name}: {cmd.cmd.strip()}")

        # set last command = cmd
        self.last_cmd = cmd

        # clear last response
        self.last_response = None

        # clear last response
        self.last_response = None

        # reset response buffer
        self.response_buffer = queue.Queue(10)

        # send command on serial
        self.huart.write(bytes(cmd.cmd, "ascii"))

        # command send time
        cmd.send_time = time.time()

        # clear cmd_idle
        self.cmd_idle.clear()

    def add_event(self, event: AtEvent) -> None:
        """
        :param event:
        :type event:
        :return:
        :rtype:
        """
        with self.event_lock:
            self.events.append(event)

    def start(self) -> None:
        """
        Starts the client instance
        :return: None
        :rtype: None
        """
        self.running.set()
        self.client_thread.start()

    def stop(self) -> None:
        """
        :return: None
        :rtype: None
        """
        self.running.clear()

        while self.client_thread.is_alive():
            time.sleep(0.1)

        self.huart.close()

    def _run(self) -> None:
        """
        :return:
        :rtype:
        """
        # response buffer
        response_buffer: str = str()

        # while client is running
        while self.running.is_set():

            # event/cmd response matching string
            match: str = str()

            # read line from uart
            response_buffer += self.huart.readline().decode("ascii")

            # get events lock
            with self.event_lock:

                # loop over a copy of added events
                for event in self.events[:]:
                    match = self.match_string(
                        event.string,
                        response_buffer,
                        event.match_type
                    )

                    # check for an event match
                    if match:
                        event.callback(event, event.string, match)
                        response_buffer = str()

                        # remove one-time events
                        if event.event_type == AtEventType.OneTime:
                            self.events.remove(event)

                        break

            # if no command response is pending, continue
            if self.cmd_idle.is_set():
                continue

            # calculate command timeout
            timeout_time: float = self.last_cmd.send_time + self.last_cmd.timeout

            # check if command timed out
            if time.time() > timeout_time:
                # command response timed out
                self.on_response(
                    self.last_cmd,
                    AtCommandStatus.Timeout,
                    None,
                    None
                )

                self.last_response = None
                self.cmd_idle.set()
                continue

            # check success response string was found in response string
            match = self.match_string(
                self.last_cmd.success_response.string,
                response_buffer,
                self.last_cmd.success_response.match_type
            )

            # check if received line matches success response
            if match:
                self.last_response = self.last_cmd.success_response
                self.on_response(
                    self.last_cmd,
                    AtCommandStatus.Success,
                    self.last_response,
                    match
                )

            # check on of error responses string was found in response string
            elif self.last_cmd.error_response:
                for err in self.last_cmd.error_response:
                    match = self.match_string(
                        err.string,
                        response_buffer,
                        err.match_type
                    )

                    if match:
                        self.last_response = err
                        self.on_response(
                            self.last_cmd,
                            AtCommandStatus.Error,
                            self.last_response,
                            match
                        )
                        break

            # check if one of other responses string was found in response string
            elif self.last_cmd.other_response:
                for rsp in self.last_cmd.other_response:
                    match = self.match_string(
                        rsp.string,
                        response_buffer,
                        rsp.match_type
                    )

                    if match:
                        self.last_response = rsp
                        self.on_response(
                            self.last_cmd,
                            AtCommandStatus.Success,
                            self.last_response,
                            match
                        )
                        break

            # reset response buffer & clear cmd_idle
            if match:
                self.cmd_idle.set()
                response_buffer = str()

            time.sleep(0.1)

    def on_response(self, cmd: AtCommand,
                    status: AtCommandStatus,
                    response: Union[AtCommandResponse, None],
                    response_string: Union[str, None]
                    ) -> None:
        """
        :param cmd:
        :type cmd:
        :param response:
        :type response:
        :param status:
        :type status:
        :param response_string:
        :type response_string:
        :return:
        :rtype:
        """
        pass

    @staticmethod
    def match_string(pattern: str, string: str, match_type: AtStringMatchingRule) -> str:
        """
        :param pattern:
        :type pattern:
        :param string:
        :type string:
        :param match_type:
        :type match_type:
        :return:
        :rtype:
        """
        # check if string matching rule == regex
        if match_type == AtStringMatchingRule.Regex:

            # check if there is a string that matches pattern regex string in the given string
            match = re.findall(pattern, string)
            if match:
                return match[0]
            else:
                return ""

        else:
            # check if pattern string exists within given string
            if pattern in string:
                return pattern

        return ""


if __name__ == '__main__':
    import sys

    log.basicConfig(stream=sys.stdout)

    def is_ready(event: AtEvent, response: AtCommandResponse, string: str) -> None:
        print(f"Ready callback. Device is ready: {string}")

    def time_update(event: AtEvent, response: AtCommandResponse, string: str) -> None:
        print(f"Device Date Time Update Callback. Date Time: {string}")

    COM_PORT = "COM6"

    # ok response
    ok_rsp = AtCommandResponse(
        name="OK",
        string="OK\r\n",
        matching=AtStringMatchingRule.Exact
    )

    # date send_time response
    dt_rsp = AtCommandResponse(
        name="Date Time",
        string="\\+CCLK=.*\r\n",
        matching=AtStringMatchingRule.Regex
    )

    # cme error
    cme_error = AtCommandResponse(
        name="CME Error",
        string="\\+CME ERROR=\\d+\r\n",
        matching=AtStringMatchingRule.Regex
    )

    # cms error
    cms_error = AtCommandResponse(
        name="CMS Error",
        string="\\+CMS ERROR=\\d+\r\n",
        matching=AtStringMatchingRule.Regex
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

    # date-send_time command
    at_dt = AtCommand(
        name="AT Date Time",
        cmd="AT+CCLK?\r\n",
        success_response=ok_rsp,
        timeout=3
    )

    # multiline command
    at_multiline = AtCommand(
        name="AT Multiline",
        cmd="AT+ML?\r\n",
        success_response=ok_rsp,
        timeout=3
    )

    # timeout
    at_timeout = AtCommand(
        name="AT Timeout",
        cmd="AT+TIMEOUT\r\n",
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

    # ready event
    dt_update = AtEvent(
        name="Date Time Update",
        string="\\+CCLK:\\s*.*\r\n",
        event_type=AtEventType.Reoccurring,
        matching=AtStringMatchingRule.Regex,
        callback=time_update
    )

    # # print responses
    # print(ok_rsp)
    # print(dt_rsp)
    # print(cme_error)
    # print(cms_error)
    # print("-----------------------------")
    #
    # # print commands
    # print(at_check)
    # print("-----------------------------")
    #
    # print(at_cme)
    # print("-----------------------------")
    #
    # print(at_cms)
    # print("-----------------------------")
    #
    # print(at_dt)
    # print("-----------------------------")
    #
    # print(at_timeout)
    # print("-----------------------------")

    got_response = threading.Event()


    def on_response(
        cmd: AtCommand,
        status: AtCommandStatus,
        response: Union[AtCommandResponse, None],
        response_string: Union[str, None]
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
        print(f"Received event: {event.name}, string: {string}, response: {response}")


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
        cl.send_cmd(at_dt)
        got_response.wait()
        print(cl)
        print("-----------------------------")

        got_response.clear()
        cl.send_cmd(at_multiline)
        got_response.wait()
        print(cl)
        print("-----------------------------")

        got_response.clear()
        cl.send_cmd(at_timeout)
        got_response.wait()
        print(cl)
        print("-----------------------------")
        
        # send events & close
        print("Waiting for events. Press q to close. ")
        close = ""
        while close != 'q':
            close = input().strip().lower()
        cl.stop()
