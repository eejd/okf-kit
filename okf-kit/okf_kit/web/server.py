"""Local read-only web UI for an OKF bundle — `okf serve`.

On-demand, localhost-bound, stdlib-only HTTP server. Serves a vanilla-JS SPA and
a JSON API over the existing core (parse/search/context/links/validate). Launched
by a harness/agent when a human wants to browse the bundle visually; it is NOT
started by `okf-mcp`. Concept ids flow through ``resolve_cid_path`` and static
paths are contained to ``static/``.
"""
from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from okf_kit.core.links import (
    build_adjacency,
    build_backlinks,
    iter_concept_files,
    resolve_cid_path,
)
from okf_kit.core.parse import parse_concept
from okf_kit.core.search import Hit, build_index
from okf_kit.core.search import search as run_search
from okf_kit.core.validate import validate_bundle

STATIC_DIR = Path(__file__).resolve().parent / "static"


@dataclass
class Response:
    status: int
    content_type: str
    body: bytes


def _json(obj: Any, status: int = 200) -> Response:
    return Response(
        status, "application/json; charset=utf-8", json.dumps(obj, default=str).encode("utf-8")
    )


def _not_found() -> Response:
    return Response(404, "application/json", b'{"error":"not found"}')


def route(method: str, path: str, bundle_root: Path) -> Response:
    """Pure router: map a (method, path) to a Response. Tested without sockets."""
    if method != "GET":
        return Response(405, "application/json", b'{"error":"method not allowed"}')
    parsed = urlparse(path)
    seg = parsed.path
    qs = parse_qs(parsed.query)
    root = Path(bundle_root).resolve()

    if seg == "/api/index":
        return _api_index(root)
    if seg == "/api/validate":
        return _json(validate_bundle(root).to_dict())
    if seg == "/api/graph":
        return _api_graph(root)
    if seg.startswith("/api/search"):
        return _api_search(root, qs)
    if seg.startswith("/api/backlinks/"):
        return _json(_backlinks(root, unquote(seg[len("/api/backlinks/") :])))
    if seg.startswith("/api/concepts/"):
        return _api_concept(root, unquote(seg[len("/api/concepts/") :]), _int(qs, "depth", 0))
    return _static(path)


def _int(qs: dict[str, list[str]], key: str, default: int) -> int:
    try:
        return int(qs.get(key, [str(default)])[0])
    except (ValueError, IndexError):
        return default


def _api_index(root: Path) -> Response:
    index = build_index(root)
    types = sorted({d.type for d in index.docs if d.type})
    tags = sorted({t for d in index.docs for t in d.tags})
    return _json({"concepts": index.to_dict(), "types": types, "tags": tags})


def _api_graph(root: Path) -> Response:
    concepts = [parse_concept(md, root) for md in iter_concept_files(root)]
    adjacency = build_adjacency(root, concepts)
    nodes = [
        {
            "data": {
                "id": c.cid,
                "label": c.frontmatter.get("title") or c.cid,
                "type": _as_str(c.frontmatter.get("type")),
            }
        }
        for c in concepts
        if c.reserved is None
    ]
    edges = [
        {"data": {"id": f"{src}->{tgt}", "source": src, "target": tgt}}
        for src, targets in adjacency.items()
        for tgt in targets
    ]
    return _json({"elements": nodes + edges})


def _api_search(root: Path, qs: dict[str, list[str]]) -> Response:
    q = qs.get("q", [""])[0] if qs.get("q") else ""
    limit = _int(qs, "limit", 20)
    hits = run_search(build_index(root), q, type=qs.get("type"), tag=qs.get("tag"), limit=limit)
    return _json([_hit_dict(h) for h in hits])


def _api_concept(root: Path, cid: str, depth: int) -> Response:
    del depth  # reserved for v2 neighborhood view; reader uses a single concept
    path = resolve_cid_path(root, cid)
    if path is None:
        return _not_found()
    concept = parse_concept(path, root)
    all_concepts = [parse_concept(md, root) for md in iter_concept_files(root)]
    adjacency = build_adjacency(root, all_concepts)
    backlinks = build_backlinks(adjacency)
    return _json(
        {
            "cid": concept.cid,
            "path": str(path.relative_to(root)),
            "frontmatter": concept.frontmatter,
            "frontmatter_error": concept.frontmatter_error,
            "body": concept.body,
            "outgoing": adjacency.get(cid, []),
            "backlinks": backlinks.get(cid, []),
        }
    )


def _backlinks(root: Path, cid: str) -> list[str]:
    if resolve_cid_path(root, cid) is None:
        return []
    concepts = [parse_concept(md, root) for md in iter_concept_files(root)]
    return build_backlinks(build_adjacency(root, concepts)).get(cid, [])


def _hit_dict(hit: Hit) -> dict[str, object]:
    return {
        "cid": hit.cid,
        "title": hit.title,
        "type": hit.type,
        "snippet": hit.snippet,
        "score": hit.score,
    }


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _static(path: str) -> Response:
    rel = unquote(urlparse(path).path).lstrip("/") or "index.html"
    target = (STATIC_DIR / rel).resolve()
    static_root = STATIC_DIR.resolve()
    try:
        target.relative_to(static_root)
    except ValueError:
        return Response(403, "text/plain", b"forbidden")
    if target.is_file():
        return _serve_file(target)
    index = STATIC_DIR / "index.html"
    if index.is_file():
        return _serve_file(index)
    return _not_found()


def _serve_file(path: Path) -> Response:
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return Response(200, ctype, path.read_bytes())


def make_handler(bundle_root: Path) -> type[BaseHTTPRequestHandler]:
    """Build a request-handler class bound to ``bundle_root``."""
    root = Path(bundle_root).resolve()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            resp = route("GET", self.path, root)
            self.send_response(resp.status)
            self.send_header("Content-Type", resp.content_type)
            self.send_header("Content-Length", str(len(resp.body)))
            self.end_headers()
            self.wfile.write(resp.body)

        def log_message(self, fmt: str, *args: Any) -> None:  # silence default logging
            pass

    return Handler


def serve(bundle: Path, host: str = "127.0.0.1", port: int = 0) -> int:
    """Start the web server (blocks until interrupted). Returns the bound port."""
    root = Path(bundle).resolve()
    httpd = ThreadingHTTPServer((host, port), make_handler(root))
    actual_port = httpd.server_address[1]
    print(f"okf serve: '{root.name}' at http://{host}:{actual_port}  (Ctrl-C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nokf serve: stopping.")
    finally:
        httpd.server_close()
    return actual_port
