#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from unittest import TestCase
import sys
import serial
from serial import Serial
from at_cmd_client import AtStringMatchingRule, AtCommand, AtCommandResponse, AtCommandClient, AtCommandStatus


class Test(TestCase):

    # serial port
    SERIAL_PORT = "COM6"
    SERIAL_BR = 115200

    # ok response
    OK_RSP = AtCommandResponse(
        name="OK",
        string="OK\r\n",
        matching=AtStringMatchingRule.Exact
    )

    # date time response
    DT_RSP = AtCommandResponse(
        name="Date Time",
        string="\\+CCLK=.*\r\n",
        matching=AtStringMatchingRule.Regex
    )

    # cme error
    CME_ERR_RSP = AtCommandResponse(
        name="CME Error",
        string="\\+CME ERROR=\\d+\r\n",
        matching=AtStringMatchingRule.Regex
    )

    # cms error
    CMS_ERR_RSP = AtCommandResponse(
        name="CMS Error",
        string="\\+CMS ERROR=\\d+\r\n",
        matching=AtStringMatchingRule.Regex
    )

    # at command: AT
    AT_CHECK = AtCommand(
        name="AT Check",
        cmd="AT\r\n",
        success_response=OK_RSP,
        error_response=[CME_ERR_RSP, CMS_ERR_RSP],
        timeout=3
    )

    # cme error command
    AT_CME = AtCommand(
        name="AT CME Error",
        cmd="AT+ERROR=CME\r\n",
        success_response=OK_RSP,
        error_response=[CME_ERR_RSP, CMS_ERR_RSP],
        timeout=3
    )

    # cms error command
    AT_CMS = AtCommand(
        name="AT CMS Error",
        cmd="AT+ERROR=CMS\r\n",
        success_response=OK_RSP,
        error_response=[CME_ERR_RSP, CMS_ERR_RSP],
        timeout=3
    )

    # date-time command
    AT_DT = AtCommand(
        name="AT Date Time",
        cmd="AT+CCLK?\r\n",
        success_response=DT_RSP,
        error_response=[CME_ERR_RSP, CMS_ERR_RSP],
        timeout=3
    )

    # timeout
    AT_TIMEOUT = AtCommand(
        name="AT Date Time",
        cmd="AT+TIMEOUT\r\n",
        success_response=OK_RSP,
        error_response=[CME_ERR_RSP, CMS_ERR_RSP],
        timeout=3
    )

    def test_at_client_send_command(self) -> None:
        with serial.Serial(port=self.SERIAL_PORT, baudrate=self.SERIAL_BR) as serial_port:
            client = AtCommandClient(name=__name__, uart_handle=serial_port)
            status = client.send_cmd(self.AT_CHECK)
            self.assertEqual(status, AtCommandStatus.Success, f"AT Command {self.AT_CHECK} status: {status}")
            self.assertIn(self.AT_CHECK.success_response.string, client.response_buffer.decode("ascii"))


if __name__ == '__main__':
    pass
