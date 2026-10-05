"""Synthetic files and Canvas records for isolated UX-4 QA only."""
from pathlib import Path
import base64
import os
from smarti.canvas_model import new_canvas_artifact


def seed_workbench(service, session_id):
    profile = Path(os.environ["SMARTI_DATA_DIR"]).resolve()
    root = profile / "ux4-workbench"
    root.mkdir(parents=True, exist_ok=True)
    service.core.local_gateway._workspace.set_root(str(root))
    assert Path(service.core.local_gateway._workspace.root()).resolve() == root
    (root / "folder").mkdir(parents=True, exist_ok=True)
    (root / "folder" / "notes.md").write_text("# UX-4 document\n\n" + "\n\n".join(f"Line {n} — Hebrew English test content" for n in range(250)), encoding="utf-8")
    (root / "image.png").write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQAAAABJRU5ErkJggg=="))
    (root / "unsupported.ux4").write_text("Isolated Open With fixture", encoding="utf-8")
    # One valid PDF page, including exact xref offsets, without a fixture dependency.
    stream = b"BT /F1 18 Tf 40 740 Td (UX-4 native PDF reading) Tj ET"
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>", b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"]
    data = b"%PDF-1.4\n"; offsets = []
    for index, value in enumerate(objects, 1):
        offsets.append(len(data)); data += f"{index} 0 obj\n".encode() + value + b"\nendobj\n"
    xref = len(data); data += b"xref\n0 6\n0000000000 65535 f \n" + b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets)
    data += f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    (root / "reading.pdf").write_bytes(data)
    canvases = [new_canvas_artifact({"canvas_id": f"ux4-canvas-{n}", "title": f"Canvas {n}",
                 "html": f'<h1>Canvas {n}</h1><button id="ask">Ask Smarti</button>',
                 "buttons": [{"id": "ask", "label": "Ask Smarti", "action": "inspect", "target": f"canvas-{n}"}]}) for n in (1, 2)]
    service.core.chat_store.append_message("assistant", "UX-4 Canvas references", session_id=session_id, metadata={"canvases": canvases})
    return {"root": str(root), "canvases": [item["id"] for item in canvases]}
