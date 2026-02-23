from __future__ import annotations

import json
import logging
import os
import socket
import threading
from pathlib import Path
from typing import Any, Callable

Request = dict[str, Any]
Response = dict[str, Any]
RequestHandler = Callable[[Request], Response]


class IpcError(RuntimeError):
  pass


class JsonIpcServer:
  def __init__(
    self,
    socket_path: str | Path,
    handler: RequestHandler,
    *,
    logger: logging.Logger | None = None,
  ) -> None:
    self.socket_path = Path(socket_path).expanduser()
    self.handler = handler
    self.logger = logger or logging.getLogger("lifesuspend.ipc")

    self._server_sock: socket.socket | None = None
    self._accept_thread: threading.Thread | None = None
    self._stop_event = threading.Event()

  def start(self) -> None:
    self.socket_path.parent.mkdir(parents=True, exist_ok=True)
    if self.socket_path.exists():
      self.socket_path.unlink()

    self._stop_event.clear()
    self._server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    self._server_sock.bind(str(self.socket_path))
    os.chmod(self.socket_path, 0o600)
    self._server_sock.listen(16)
    self._server_sock.settimeout(0.5)

    self._accept_thread = threading.Thread(
      target=self._accept_loop,
      name="lifesuspend-ipc",
      daemon=True,
    )
    self._accept_thread.start()

  def stop(self) -> None:
    self._stop_event.set()

    if self._server_sock is not None:
      try:
        self._server_sock.close()
      except OSError:
        pass
      self._server_sock = None

    if self._accept_thread is not None and self._accept_thread.is_alive():
      self._accept_thread.join(timeout=2)

    if self.socket_path.exists():
      self.socket_path.unlink(missing_ok=True)

  def _accept_loop(self) -> None:
    assert self._server_sock is not None

    while not self._stop_event.is_set():
      try:
        conn, _ = self._server_sock.accept()
      except socket.timeout:
        continue
      except OSError:
        if self._stop_event.is_set():
          break
        self.logger.exception("Error aceptando conexion IPC")
        break

      worker = threading.Thread(
        target=self._handle_client,
        args=(conn,),
        daemon=True,
      )
      worker.start()

  def _handle_client(self, conn: socket.socket) -> None:
    with conn:
      try:
        raw_line = _read_line(conn)
      except ValueError as exc:
        _send_response(conn, {"ok": False, "state": "hidden", "details": str(exc)})
        return

      if not raw_line:
        _send_response(conn, {"ok": False, "state": "hidden", "details": "Solicitud vacia"})
        return

      try:
        payload = json.loads(raw_line)
      except json.JSONDecodeError:
        _send_response(
          conn,
          {
            "ok": False,
            "state": "hidden",
            "details": "JSON invalido",
          },
        )
        return

      if not isinstance(payload, dict):
        _send_response(
          conn,
          {
            "ok": False,
            "state": "hidden",
            "details": "Formato de solicitud invalido",
          },
        )
        return

      try:
        response = self.handler(payload)
      except Exception:
        self.logger.exception("Handler IPC fallo")
        response = {
          "ok": False,
          "state": "hidden",
          "details": "Error interno del daemon",
        }

      _send_response(conn, response)


def _read_line(conn: socket.socket, *, max_bytes: int = 128_000) -> str:
  buf = bytearray()
  while True:
    chunk = conn.recv(4096)
    if not chunk:
      break
    buf.extend(chunk)
    if len(buf) > max_bytes:
      raise ValueError("Solicitud demasiado grande")
    if b"\n" in chunk:
      break

  if not buf:
    return ""

  line = bytes(buf).split(b"\n", 1)[0]
  return line.decode("utf-8", errors="replace")


def _send_response(conn: socket.socket, response: Response) -> None:
  payload = json.dumps(response, separators=(",", ":")) + "\n"
  conn.sendall(payload.encode("utf-8"))


def send_payload(
  socket_path: str | Path,
  payload: Request,
  *,
  timeout_sec: float = 2.0,
) -> Response:
  sock_path = Path(socket_path).expanduser()

  with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
    conn.settimeout(timeout_sec)
    try:
      conn.connect(str(sock_path))
    except OSError as exc:
      raise IpcError(f"No se pudo conectar al socket: {sock_path}") from exc

    body = json.dumps(payload, separators=(",", ":")) + "\n"
    conn.sendall(body.encode("utf-8"))

    try:
      raw = _read_line(conn)
    except (OSError, ValueError) as exc:
      raise IpcError("No se pudo leer respuesta del daemon") from exc

  if not raw:
    raise IpcError("El daemon no devolvio respuesta")

  try:
    parsed = json.loads(raw)
  except json.JSONDecodeError as exc:
    raise IpcError("Respuesta JSON invalida") from exc

  if not isinstance(parsed, dict):
    raise IpcError("Respuesta IPC invalida")

  return parsed


def send_command(
  socket_path: str | Path,
  command: str,
  *,
  timeout_sec: float = 2.0,
) -> Response:
  return send_payload(
    socket_path,
    {"cmd": command},
    timeout_sec=timeout_sec,
  )
