#!/usr/bin/env python3
"""Serve the guided scheduling demo and collect submissions."""

from __future__ import annotations

import argparse
import http.server
import json
import socketserver
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
import re


def main() -> None:
  parser = argparse.ArgumentParser(description="Serve guided scheduling demo with submission API.")
  parser.add_argument("--host", default="127.0.0.1", help="Bind host, e.g. 127.0.0.1 or 0.0.0.0")
  parser.add_argument("--port", type=int, default=8000, help="Bind port")
  args = parser.parse_args()

  demo_dir = Path(__file__).resolve().parent / "scheduling_demo_guided"
  submissions_dir = Path(__file__).resolve().parent / "submissions"
  submissions_dir.mkdir(parents=True, exist_ok=True)
  submissions_file = submissions_dir / "scheduling_submissions.jsonl"
  handler = http.server.SimpleHTTPRequestHandler

  class DemoHandler(handler):
    def __init__(self, *args, **kwargs):
      super().__init__(*args, directory=str(demo_dir), **kwargs)

    def _send_json(self, status_code: int, payload: dict) -> None:
      body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
      self.send_response(status_code)
      self.send_header("Content-Type", "application/json; charset=utf-8")
      self.send_header("Content-Length", str(len(body)))
      self.end_headers()
      self.wfile.write(body)

    def _safe_filename(self, filename: str) -> str:
      name = filename.strip().replace("\\", "/").split("/")[-1]
      name = re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", name)
      if not name:
        name = "upload.bin"
      return name[:180]

    def _parse_multipart(self, raw: bytes, boundary: bytes) -> list[dict]:
      delimiter = b"--" + boundary
      parts = raw.split(delimiter)
      parsed_parts: list[dict] = []
      for part in parts[1:]:
        if not part or part in (b"--", b"--\r\n"):
          continue
        if part.startswith(b"\r\n"):
          part = part[2:]
        if part.endswith(b"\r\n"):
          part = part[:-2]
        if part.endswith(b"--"):
          part = part[:-2]

        header_blob, sep, body = part.partition(b"\r\n\r\n")
        if not sep:
          continue
        headers = {}
        for line in header_blob.split(b"\r\n"):
          if b":" not in line:
            continue
          k, v = line.split(b":", 1)
          headers[k.decode("latin1").strip().lower()] = v.decode("latin1").strip()

        disp = headers.get("content-disposition", "")
        if not disp:
          continue
        name_match = re.search(r'name="([^"]+)"', disp)
        file_match = re.search(r'filename="([^"]*)"', disp)
        field_name = name_match.group(1) if name_match else ""
        filename = file_match.group(1) if file_match else None

        parsed_parts.append(
          {
            "field_name": field_name,
            "filename": filename,
            "content_type": headers.get("content-type", "application/octet-stream"),
            "content": body,
          }
        )
      return parsed_parts

    def _save_submission(self, payload: dict, files: list[dict], submissions_file: Path) -> dict:
      now = datetime.now(timezone.utc)
      submission_id = f"sub_{now.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
      submission_dir = submissions_file.parent / submission_id
      tables_dir = submission_dir / "tables"
      tables_dir.mkdir(parents=True, exist_ok=True)

      saved_files = []
      filename_counter: dict[str, int] = {}
      for idx, f in enumerate(files):
        raw_name = f.get("filename") or f"file_{idx + 1}.bin"
        safe_name = self._safe_filename(raw_name)
        count = filename_counter.get(safe_name, 0)
        filename_counter[safe_name] = count + 1
        if count > 0:
          stem, dot, ext = safe_name.partition(".")
          safe_name = f"{stem}_{count}.{ext}" if dot else f"{safe_name}_{count}"

        out_path = tables_dir / safe_name
        out_path.write_bytes(f["content"])
        source_field = f.get("field_name", "")
        source_input = source_field.replace("files__", "", 1) if source_field.startswith("files__") else source_field
        saved_files.append(
          {
            "source_input": source_input,
            "original_filename": raw_name,
            "saved_filename": safe_name,
            "size_bytes": len(f["content"]),
            "content_type": f.get("content_type", "application/octet-stream"),
          }
        )

      requirement_info_path = submission_dir / "requirement_info.json"
      requirement_info_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

      record = {
        "submission_id": submission_id,
        "received_at_utc": now.isoformat(),
        "client_ip": self.client_address[0],
        "user_agent": self.headers.get("User-Agent", ""),
        "requirement_info_path": str(requirement_info_path),
        "tables_dir": str(tables_dir),
        "saved_file_count": len(saved_files),
        "saved_files": saved_files,
      }

      with submissions_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

      return {
        "ok": True,
        "submission_id": submission_id,
        "saved_file_count": len(saved_files),
        "submission_dir": str(submission_dir),
        "requirement_info_path": str(requirement_info_path),
        "tables_dir": str(tables_dir),
      }

    def do_POST(self) -> None:  # noqa: N802
      parsed = urlparse(self.path)
      if parsed.path != "/api/submissions":
        self.send_error(404, "Not Found")
        return

      length = int(self.headers.get("Content-Length", "0"))
      if length <= 0 or length > 200 * 1024 * 1024:
        self._send_json(400, {"ok": False, "error": "Invalid payload size"})
        return

      raw = self.rfile.read(length)
      content_type = self.headers.get("Content-Type", "")

      payload: dict | None = None
      files: list[dict] = []

      if content_type.startswith("multipart/form-data"):
        boundary_match = re.search(r"boundary=([^;]+)", content_type)
        if not boundary_match:
          self._send_json(400, {"ok": False, "error": "Missing multipart boundary"})
          return
        boundary = boundary_match.group(1).strip().strip('"').encode("utf-8")
        parts = self._parse_multipart(raw, boundary)
        for p in parts:
          field_name = p.get("field_name", "")
          filename = p.get("filename")
          if filename is None and field_name == "payload":
            try:
              payload = json.loads(p["content"].decode("utf-8"))
            except json.JSONDecodeError:
              self._send_json(400, {"ok": False, "error": "Field 'payload' must be valid JSON"})
              return
          elif filename is not None and field_name.startswith("files__"):
            files.append(p)
      else:
        try:
          payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
          self._send_json(400, {"ok": False, "error": "Payload must be valid JSON"})
          return

      if not isinstance(payload, dict):
        self._send_json(400, {"ok": False, "error": "Payload must be a JSON object"})
        return

      result = self._save_submission(payload, files, submissions_file)
      self._send_json(200, result)

  with socketserver.TCPServer((args.host, args.port), DemoHandler) as httpd:
    print(f"[Guided Scheduling Demo] Serving: {demo_dir}")
    print(f"[Guided Scheduling Demo] URL: http://{args.host}:{args.port}")
    print(f"[Guided Scheduling Demo] Submissions file: {submissions_file}")
    print("[Guided Scheduling Demo] Press Ctrl+C to stop.")
    httpd.serve_forever()


if __name__ == "__main__":
  main()
