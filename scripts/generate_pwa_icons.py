from pathlib import Path


def load_font(size: int):
    try:
        from PIL import ImageFont
    except ImportError as exc:
        raise RuntimeError("Pillow is required to generate icons") from exc

    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/SFNS.ttf",
    ]
    for font_path in font_candidates:
        try:
            return ImageFont.truetype(font_path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def generate_icon(size: int, text: str, output_path: Path) -> None:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (size, size), (0, 0, 0))
    draw = ImageDraw.Draw(image)
    font = load_font(int(size * 0.42))

    try:
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    except Exception:
        text_width, text_height = draw.textsize(text, font=font)

    position = ((size - text_width) / 2, (size - text_height) / 2)
    draw.text(position, text, fill=(255, 255, 255), font=font)
    image.save(output_path, format="PNG")


def main() -> None:
    icon_dir = Path("rss/app/static/icons")
    icon_dir.mkdir(parents=True, exist_ok=True)

    generate_icon(192, "RSS", icon_dir / "icon-192.png")
    generate_icon(512, "RSS", icon_dir / "icon-512.png")
    generate_icon(180, "RSS", icon_dir / "apple-icon-180.png")


if __name__ == "__main__":
    main()
