"""Render the README media from one successful local-only demo (requires Pillow)."""
from argparse import ArgumentParser
import json
from pathlib import Path
from shutil import copyfile

from PIL import Image, ImageDraw, ImageFont


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--ui-font", required=True, type=Path)
    parser.add_argument("--mono-font", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    report = json.loads((args.capture / "desktop-e2e.json").read_text(encoding="utf-8"))
    if report["outcome"] != "passed" or report["fixture_login_submissions"] != 1 or report["logout_requests"] != 0:
        raise SystemExit("Media requires a successful, isolated demo.")
    raw = (args.capture / "terminal.txt").read_bytes()
    transcript = raw.decode("utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig").splitlines()
    transcript = [line for line in transcript if line.strip()]
    if transcript != [
        "Demo uses a loopback portal and an isolated browser profile.",
        f"PASS  Desktop journey: {len(report['checks'])} checks",
        "      Loopback login submissions: 1",
        "      Portal logout requests:     0",
        r"      Report: runtime\demo\desktop-e2e.json",
    ]:
        raise SystemExit("Unexpected terminal transcript; review it before sharing.")

    out = root / "docs/media"
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
    for source, target in (("online", "status"), ("logs", "logs"), ("paused", "paused")):
        copyfile(args.capture / f"desktop-{source}.png", out / f"{target}.png")
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

    terminal = Image.new("RGB", (936, 260), "#14221c")
    draw = ImageDraw.Draw(terminal)
    font = ImageFont.truetype(args.mono_font, 19)
    draw.rectangle((0, 0, 935, 43), fill="#20332a")
    draw.text((24, 12), "PowerShell · 回环演练", font=label_font, fill="#e6f3ed")
    draw.text((24, 62), r"PS> .\demo.ps1 -SkipBuild", font=font, fill="#aef1d4")
    for index, line in enumerate(transcript):
        draw.text((24, 108 + 24 * index), line, font=font,
                  fill="#aef1d4" if line.startswith("PASS") else "#e5ede9")
    terminal.save(out / "terminal.png", optimize=True)


if __name__ == "__main__":
    main()
