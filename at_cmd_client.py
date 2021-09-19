#!/usr/bin/env python3
# -*- coding; utf-8 -*-


import enum
import logging as log
import re
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


class AtEvent(AtString):
    """AT Event"""

    def __str__(self) -> str:
        return f"AT Event {self.name} string: {self.string.strip()}\n"


class AtCommand(object):
    """AT Command"""

    def __init__(self, name: str,
                 cmd: str,
                 success_response: Union[AtCommandResponse, None],
                 error_response: Union[List[AtCommandResponse], None] = None,
                 other_response: Union[List[AtCommandResponse], None] = None,
                 timeout: int = 0) -> None:
        self.name = name
        self.cmd = cmd
        self.timeout = timeout
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
        self.response_buffer: Union[str, bytes] = ""
        self.last_cmd: Union[AtCommand, None] = None
        self.last_response: Union[AtCommandResponse, None] = None

        # ---------------------------------------------------------------------------
        # self.cmd_queue = queue.Queue()
        # self.event_queue = queue.Queue()
        # self.event_callbacks: Dict[AtEvent: callable[[AtEvent, str], None]] = dict()
        # ---------------------------------------------------------------------------

    def __str__(self) -> str:
        string = f"Module: {self.name}\n"

        if self.last_cmd:
            string += f"last command: {self.last_cmd.name} string: {self.last_cmd.cmd.strip()}\n"

        if self.last_response:
            string += f"last response: {self.last_response.name} string: {self.last_response.string.strip()}\n"

        string += f"response buffer: {self.response_buffer}\n"

        return string

    # def send_cmd(self, cmd: AtCommand) -> None:
    #     pass

    def send_cmd(self, cmd: AtCommand) -> AtCommandStatus:
        """
        Send command on UART
        :param cmd: Command to be sent to GSM module over UART
        :type cmd: AtCommand
        :return: AtCommandStatus:
            AtCommandStatus.Success: If response string matches success, or one of other responses
            AtCommandStatus.Error: If response string matches one of error responses
            AtCommandStatus.timeout: If no response was received within command timeout period
        :rtype: AtCommandStatus
        """

        self.logger.debug(f"Sending cmd {cmd.name}: {cmd.cmd.strip()}")

        # at command response string
        response = b""

        # at command status
        ret_status = AtCommandStatus.Timeout

        # set last command = cmd
        self.last_cmd = cmd

        # clear last response
        self.last_response = None

        # send command on serial
        self.huart.write(bytes(cmd.cmd, "ascii"))

        # calculate command timeout
        end_time = time.time() + cmd.timeout

        # check if command timed out or a response was received
        while (time.time() < end_time) and (ret_status == AtCommandStatus.Timeout):

            # read line from UART
            response += self.huart.readline()

            # check success response string was found in response string
            if self.match_string(cmd.success_response.string, response.decode("ascii"), cmd.success_response.match_type):
                self.last_response = cmd.success_response
                ret_status = AtCommandStatus.Success

            # check on of error responses string was found in response string
            elif cmd.error_response:
                for err in cmd.error_response:
                    if self.match_string(err.string, response.decode("ascii"), err.match_type):
                        self.last_response = err
                        ret_status = AtCommandStatus.Error

            # check if one of other responses string was found in response string
            elif cmd.other_response:
                for rsp in cmd.other_response:
                    if self.match_string(rsp.string, response.decode("ascii"), rsp.match_type):
                        self.last_response = rsp
                        ret_status = AtCommandStatus.Success

            # wait for 100 msec
            time.sleep(0.1)

        # set response buffer
        self.response_buffer = response

        if self.last_response:
            self.logger.debug(f"Response buffer {self.last_response.name}: {self.response_buffer}")

        return ret_status

    @staticmethod
    def match_string(pattern: str, string: str, match_type: AtStringMatchingRule) -> bool:

        # check if string matching rule == regex
        if match_type == AtStringMatchingRule.Regex:

            # check if there is a string that matches pattern regex string in the given string
            match = re.findall(pattern, string)
            return bool(match)

        else:
            # check if pattern string exists within given string
            return pattern in string


if __name__ == '__main__':
    import sys

    log.basicConfig(stream=sys.stdout)

    COM_PORT = "COM6"

    # ok response
    ok_rsp = AtCommandResponse(
        name="OK",
        string="OK\r\n",
        matching=AtStringMatchingRule.Exact
    )

    # date time response
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
        error_response=[cme_error, cms_error],
        timeout=10
    )

    # cme error command
    at_cme = AtCommand(
        name="AT CME Error",
        cmd="AT+ERROR=CME\r\n",
        success_response=ok_rsp,
        error_response=[cme_error, cms_error],
        timeout=10
    )

    # cms error command
    at_cms = AtCommand(
        name="AT CMS Error",
        cmd="AT+ERROR=CMS\r\n",
        success_response=ok_rsp,
        error_response=[cme_error, cms_error],
        timeout=10
    )

    # date-time command
    at_dt = AtCommand(
        name="AT Date Time",
        cmd="AT+CCLK?\r\n",
        success_response=dt_rsp,
        error_response=[cme_error, cms_error],
        timeout=10
    )

    # timeout
    at_timeout = AtCommand(
        name="AT Date Time",
        cmd="AT+TIMEOUT\r\n",
        success_response=ok_rsp,
        error_response=[cme_error, cms_error],
        timeout=10
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

    with serial.Serial("COM6", baudrate=115200, timeout=0.1) as ser:
        cl = AtCommandClient('testClient', ser)

        # send commands
        print(cl.send_cmd(at_check))
        print(cl)
        print("-----------------------------")

        print(cl.send_cmd(at_cme))
        print(cl)
        print("-----------------------------")

        print(cl.send_cmd(at_cms))
        print(cl)
        print("-----------------------------")

        print(cl.send_cmd(at_dt))
        print(cl)
        print("-----------------------------")

        print(cl.send_cmd(at_timeout))
        print(cl)
        print("-----------------------------")
