from __future__ import annotations

import json
import socket
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

from lifesuspend.ipc import JsonIpcServer, send_command


class IpcTests(unittest.TestCase):
  def setUp(self) -> None:
    self.tmp = tempfile.TemporaryDirectory()
    self.socket_path = Path(self.tmp.name) / "lifesuspend.sock"
    self.server: JsonIpcServer | None = None

  def tearDown(self) -> None:
    if self.server is not None:
      self.server.stop()
    self.tmp.cleanup()

  def _start_server(self, handler) -> None:
    self.server = JsonIpcServer(self.socket_path, handler)
    self.server.start()

    for _ in range(60):
      if self.socket_path.exists():
        return
      time.sleep(0.01)

    self.fail("socket IPC no disponible")

  def test_valid_command_and_state_transition(self) -> None:
    state = {"value": "hidden"}

    def handler(payload: dict[str, Any]) -> dict[str, Any]:
      cmd = payload.get("cmd")
      if cmd == "show":
        state["value"] = "visible"
        return {"ok": True, "state": state["value"], "details": "shown"}
      return {"ok": False, "state": state["value"], "details": "invalid"}

    self._start_server(handler)

    response = send_command(self.socket_path, "show")
    self.assertTrue(response["ok"])
    self.assertEqual(response["state"], "visible")

  def test_invalid_command(self) -> None:
    def handler(payload: dict[str, Any]) -> dict[str, Any]:
      cmd = str(payload.get("cmd", ""))
      if cmd not in {"show", "hide", "lock", "reload", "status"}:
        return {"ok": False, "state": "hidden", "details": f"unsupported:{cmd}"}
      return {"ok": True, "state": "hidden", "details": "ok"}

    self._start_server(handler)

    response = send_command(self.socket_path, "nope")
    self.assertFalse(response["ok"])
    self.assertIn("unsupported", response["details"])

  def test_invalid_json_request(self) -> None:
    def handler(_payload: dict[str, Any]) -> dict[str, Any]:
      return {"ok": True, "state": "hidden", "details": "ok"}

    self._start_server(handler)

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
      conn.connect(str(self.socket_path))
      conn.sendall(b"{broken-json\n")
      raw = conn.recv(4096).decode("utf-8").strip()

    response = json.loads(raw)
    self.assertFalse(response["ok"])
    self.assertIn("JSON", response["details"])

  def test_lock_command_dispatch(self) -> None:
    calls = {"lock": 0}

    def handler(payload: dict[str, Any]) -> dict[str, Any]:
      cmd = payload.get("cmd")
      if cmd == "lock":
        calls["lock"] += 1
        return {"ok": True, "state": "locking", "details": "locking"}
      return {"ok": True, "state": "hidden", "details": "ok"}

    self._start_server(handler)

    response = send_command(self.socket_path, "lock")
    self.assertTrue(response["ok"])
    self.assertEqual(response["state"], "locking")
    self.assertEqual(calls["lock"], 1)


if __name__ == "__main__":
  unittest.main()
