"""Render the README media from one successful local-only demo (requires Pillow)."""
from argparse import ArgumentParser
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--ui-font", required=True, type=Path)
    parser.add_argument("--output", type=Path, help="Defaults to docs/media.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = json.loads((args.capture / "desktop-e2e.json").read_text(encoding="utf-8"))
    if report["outcome"] != "passed" or report["fixture_login_submissions"] != 1 or report["logout_requests"] != 0:
        raise SystemExit("Media requires a successful, isolated demo.")
    out = args.output or root / "docs/media"
    out.mkdir(parents=True, exist_ok=True)
    with Image.open(root / "desktop/assets/campus-guardian.ico") as file:
        file.ico.getimage((64, 64)).save(out / "icon.png")

    captions = (
        ("first-run", "01   首次打开，填上校园网账号", 3500),
        ("wifi-join", "02   没连 Wi-Fi、也没外网，先尝试接入 SUSE", 3300),
        ("online", "03   连上 SUSE 后登录，确认外网恢复", 2900),
        ("other-wifi", "04   连着其他 Wi-Fi，即使没网也不抢占", 3300),
        ("accounts", "05   从右上角管理主账号和备用账号", 2900),
        ("logs", "06   查看登录结果，只看重要记录", 2900),
    )
    frames = []
    font = ImageFont.truetype(args.ui_font, 20)
    label_font = ImageFont.truetype(args.ui_font, 16)
    for source, label, _ in captions:
        with Image.open(args.capture / f"desktop-{source}.png") as file:
            shot = file.convert("RGB")
        shot.thumbnail((900, 570), Image.Resampling.LANCZOS)
        frame = Image.new("RGB", (936, 640), "#e8efeb")
        draw = ImageDraw.Draw(frame)
        draw.text((20, 18), label, fill="#143627", font=font)
        draw.text((916, 21), "本机回环演练", fill="#39584a", font=label_font, anchor="ra")
        frame.paste(shot, ((936 - shot.width) // 2, 54))
        frames.append(frame)
    frames[0].save(out / "desktop-flow.gif", save_all=True, append_images=frames[1:],
                   duration=[duration for _, _, duration in captions], loop=0, optimize=True)

if __name__ == "__main__":
    main()
