"""Generate extension icons from assets/lumen.ico (or plain gold squares)."""

from pathlib import Path

try:
    from PIL import Image
except ImportError:
    Image = None

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "lumen-extension" / "icons"
ICO = ROOT.parent / "assets" / "lumen.ico"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for size in (16, 48, 128):
        out = OUT / f"icon{size}.png"
        if Image and ICO.is_file():
            img = Image.open(ICO).convert("RGBA")
            img.resize((size, size), Image.Resampling.LANCZOS).save(out)
        elif Image:
            img = Image.new("RGBA", (size, size), (196, 160, 50, 255))
            img.save(out)
        else:
            raise SystemExit("pip install Pillow && python build_icons.py")
        print("Wrote", out)


if __name__ == "__main__":
    main()
