#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import threading
from unittest import TestCase
from unittest.mock import Mock

from at_cmd_client import AtCommand, AtCommandClient, AtCommandResponse, AtCommandStatus, AtStringMatchingRule


class Test(TestCase):
    # serial port
    SERIAL_PORT = "COM6"
    SERIAL_SETTINGS = {
        "baudrate": 115200,
        "timeout":  0.1
    }

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

    @staticmethod
    def client_on_at_command_response(cmd: AtCommand,
                                      status: AtCommandStatus,
                                      response: AtCommandResponse,
                                      response_buffer: str
                                      ) -> None:
        print(f"Received response for command: {cmd.name} with status: {status}")

    def client_initialized(self, client: AtCommandClient) -> None:
        """Test AtCommandClient object attributes values after initialization"""

        # client instance is AtCommandClient
        self.assertTrue(isinstance(client, AtCommandClient))

        # client name is not empty
        self.assertTrue(len(client.name.strip()) > 0)

        # serial handler thread is None @ initialization
        self.assertIsNone(client.serial_handler)

        # last command, last response & last status are None
        self.assertIsNone(client.last_cmd)
        self.assertIsNone(client.last_status)
        self.assertIsNone(client.last_response)

        # client not busy event is clear
        self.assertFalse(client.client_not_busy.is_set())

        # client thread is None @ initialization
        self.assertIsNone(client.client_thread)

        # client thread stop event is clear
        self.assertFalse(client.stop_event.is_set())

        # active thread count == 1
        self.assertEqual(threading.active_count(), 1)

    def client_started(self, client: AtCommandClient) -> None:
        """Test AtCommandClient object attributes after calling start"""

        # client not busy flag is set
        self.assertTrue(client.client_not_busy.is_set())

        # client thread stop event is clear
        self.assertFalse(client.stop_event.is_set())

        # client thread is not None
        self.assertIsNotNone(client.client_thread)

        # client thread is alive
        self.assertTrue(client.client_thread.is_alive())

        # serial handler thread is not none
        self.assertIsNotNone(client.serial_handler)

        # serial handler thread is alive
        self.assertTrue(client.serial_handler.is_alive())

        # serial port is open
        self.assertTrue(client.serial_handler.huart.isOpen())

        # active thread count == 3
        self.assertEqual(3, threading.active_count())

    def client_stopped(self, client: AtCommandClient) -> None:
        """Test AtCommandClient attribute values after stop"""

        # client stop event is set
        self.assertTrue(client.stop_event.is_set())

        # client thread is not alive
        self.assertFalse(client.client_thread.is_alive())

        # serial handler thread is not alive
        self.assertFalse(client.serial_handler.is_alive())

        # serial port is closed
        self.assertFalse(client.serial_handler.huart.isOpen())

        # active thread count == 1
        self.assertEqual(1, threading.active_count())

    def test_at_client_init(self) -> None:
        """Test ATCommandClient after initialization"""

        client = AtCommandClient(
            "TestAtClient",
            serial_port=self.SERIAL_PORT,
            serial_settings=self.SERIAL_SETTINGS
        )

        client.on_response = self.client_on_at_command_response

        self.client_initialized(client)

    def test_at_client_init_bad_serial_timeout(self) -> None:
        """Test ATCommandClient after initialization"""

        bad_config = {
            "baudrate": 115200,
        }

        self.assertRaises(Exception, lambda: AtCommandClient("badClient", self.SERIAL_PORT, bad_config))

    def test_at_client_init_bad_serial_port(self) -> None:
        """Test ATCommandClient after initialization"""

        self.assertRaises(Exception, lambda: AtCommandClient("badClient", "BAD_PORT", self.SERIAL_SETTINGS))

    def test_at_client_start_stop(self) -> None:
        """Test AtCommandClient start & stop"""

        client = AtCommandClient(
            "TestAtClient",
            serial_port=self.SERIAL_PORT,
            serial_settings=self.SERIAL_SETTINGS
        )

        client.on_response = self.client_on_at_command_response

        # start client
        client.start()
        self.client_started(client)

        # stop client
        client.stop()
        self.client_stopped(client)

    def test_at_client_start_stop_restart_stop(self) -> None:
        """Test AtCommandClient start & stop then start & stop"""

        client = AtCommandClient(
            "TestAtClient",
            serial_port=self.SERIAL_PORT,
            serial_settings=self.SERIAL_SETTINGS
        )

        client.on_response = self.client_on_at_command_response

        # start client
        client.start()
        self.client_started(client)

        # stop client
        client.stop()
        self.client_stopped(client)

        # start client again
        client.start()
        self.client_started(client)

        # stop client
        client.stop()
        self.client_stopped(client)

    def test_at_client_send_command_with_success_response(self) -> None:
        pass

    def test_at_client_send_command_with_error_response(self) -> None:
        pass

    def test_at_client_send_command_with_timeout_response(self) -> None:
        pass


if __name__ == '__main__':
    import sys
    import logging as log

    log.basicConfig(level=log.INFO, stream=sys.stderr)
