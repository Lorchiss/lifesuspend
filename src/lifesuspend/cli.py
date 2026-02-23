from __future__ import annotations

import argparse
import json
import sys
import time

from .config import resolve_socket_path
from .ipc import IpcError, send_command


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(description="lifesuspend control CLI")
  parser.add_argument(
    "command",
    choices=["show", "hide", "lock", "status", "reload", "preview"],
    help="Comando IPC a enviar al daemon",
  )
  parser.add_argument(
    "--socket",
    default=str(resolve_socket_path(None)),
    help="Ruta al socket Unix",
  )
  parser.add_argument(
    "--json",
    action="store_true",
    help="Imprime la respuesta completa en JSON",
  )
  parser.add_argument(
    "--seconds",
    type=float,
    default=5.0,
    help="Duracion para preview (solo con command=preview)",
  )
  return parser


def _print_response(command: str, response: dict[str, object], *, json_mode: bool) -> None:
  ok = bool(response.get("ok", False))

  if json_mode or command == "status":
    print(json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True))
    return

  details = str(response.get("details", "")).strip()
  state = str(response.get("state", "")).strip()
  print(details or state or ("ok" if ok else "error"))


def _run_preview(socket_path: str, seconds: float, *, json_mode: bool) -> int:
  duration = max(0.1, float(seconds))

  show_response = send_command(socket_path, "show")
  show_ok = bool(show_response.get("ok", False))

  if not show_ok:
    _print_response("show", show_response, json_mode=json_mode)
    return 1

  if not json_mode:
    print(f"Preview iniciado por {duration:.1f}s")

  time.sleep(duration)
  hide_response = send_command(socket_path, "hide")

  if json_mode:
    payload = {
      "ok": bool(hide_response.get("ok", False)),
      "details": f"Preview completado ({duration:.1f}s)",
      "duration_sec": duration,
      "show": show_response,
      "hide": hide_response,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
  else:
    _print_response("hide", hide_response, json_mode=False)

  return 0 if bool(hide_response.get("ok", False)) else 1


def main(argv: list[str] | None = None) -> int:
  parser = build_parser()
  args = parser.parse_args(argv)

  try:
    if args.command == "preview":
      return _run_preview(args.socket, args.seconds, json_mode=bool(args.json))

    response = send_command(args.socket, args.command)
  except IpcError as exc:
    print(f"error: {exc}", file=sys.stderr)
    return 1

  _print_response(args.command, response, json_mode=bool(args.json))
  return 0 if bool(response.get("ok", False)) else 1


if __name__ == "__main__":
  raise SystemExit(main())
