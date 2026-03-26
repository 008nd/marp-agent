"""Slide export helpers for PDF/PPTX/HTML/thumbnail generation."""

import subprocess
import tempfile
from pathlib import Path


def _run_marp_cli(markdown: str, output_format: str, theme: str = "gradient", editable: bool = False) -> Path:
    """Run Marp CLI and return the output file path."""
    tmpdir = tempfile.mkdtemp()
    md_path = Path(tmpdir) / "slide.md"

    if output_format == "png":
        output_path = Path(tmpdir) / "slide.png"
    else:
        output_path = Path(tmpdir) / f"slide.{output_format}"

    md_path.write_text(markdown, encoding="utf-8")

    cmd = [
        "marp",
        str(md_path),
        "--allow-local-files",
        "-o",
        str(output_path),
    ]

    if output_format == "pdf":
        cmd.append("--pdf")
    elif output_format == "pptx":
        cmd.append("--pptx")
        if editable:
            cmd.append("--pptx-editable")
    elif output_format == "html":
        cmd.append("--html")
    elif output_format == "png":
        cmd.extend(["--image", "png"])

    theme_path = Path(__file__).parent.parent / f"{theme}.css"
    if theme_path.exists():
        cmd.extend(["--theme", str(theme_path)])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"Marp CLI error: {result.stderr}")

    return output_path


def generate_pdf(markdown: str, theme: str = "gradient") -> bytes:
    return _run_marp_cli(markdown, "pdf", theme).read_bytes()


def generate_pptx(markdown: str, theme: str = "gradient") -> bytes:
    return _run_marp_cli(markdown, "pptx", theme).read_bytes()


def generate_editable_pptx(markdown: str, theme: str = "gradient") -> bytes:
    return _run_marp_cli(markdown, "pptx", theme, editable=True).read_bytes()


def generate_standalone_html(markdown: str, theme: str = "gradient") -> str:
    return _run_marp_cli(markdown, "html", theme).read_text(encoding="utf-8")


def generate_thumbnail(markdown: str, theme: str = "gradient") -> bytes:
    output_path = _run_marp_cli(markdown, "png", theme)
    png_files = sorted(output_path.parent.glob("slide*.png"))
    if not png_files:
        raise RuntimeError("Thumbnail generation failed: no PNG files created")
    return png_files[0].read_bytes()
