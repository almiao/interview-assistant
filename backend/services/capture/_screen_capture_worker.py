"""独立子进程内截屏，避免在主进程/终端线程上触发图形栈；Windows 下父进程用 CREATE_NO_WINDOW 启动，无控制台窗口。
支持区域：full, left_half, right_half, top_half, bottom_half（通过 argv[1] 传入）。"""
from __future__ import annotations

import base64
import io
import json
import sys


def _screen_capture_allowed() -> bool:
    """macOS 可能在未授权时返回壁纸，必须在实际采集进程内检查。"""
    if sys.platform != "darwin":
        return True
    import ctypes
    cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    check = getattr(cg, "CGPreflightScreenCaptureAccess", None)
    if check is None:  # macOS 10.14 及以前没有此权限接口。
        return True
    check.argtypes = []
    check.restype = ctypes.c_bool
    return bool(check())


def _cursor_position():
    """只读系统鼠标位置；不可用时回退主屏，不新增桌面依赖。"""
    import ctypes
    try:
        if sys.platform == "darwin":
            class Point(ctypes.Structure):
                _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]
            cg = ctypes.CDLL("/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
            cg.CGEventCreate.argtypes = [ctypes.c_void_p]
            cg.CGEventCreate.restype = ctypes.c_void_p
            cg.CGEventGetLocation.argtypes = [ctypes.c_void_p]
            cg.CGEventGetLocation.restype = Point
            event = cg.CGEventCreate(None)
            if not event:
                return None
            try:
                point = cg.CGEventGetLocation(event)
                return point.x, point.y
            finally:
                cf = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
                cf.CFRelease.argtypes = [ctypes.c_void_p]
                cf.CFRelease(event)
        if sys.platform == "win32":
            class Point(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            point = Point()
            if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
                return point.x, point.y
    except (OSError, AttributeError):
        pass
    return None


def _current_monitor(monitors: list[dict], position) -> dict:
    if position is not None:
        x, y = position
        for mon in monitors[1:]:
            if mon["left"] <= x < mon["left"] + mon["width"] and mon["top"] <= y < mon["top"] + mon["height"]:
                return mon
    return monitors[1]


def _region_for_monitor(mon: dict, kind: str) -> dict:
    """根据 kind 计算主显示器上的截取区域。"""
    left, top = mon["left"], mon["top"]
    w, h = mon["width"], mon["height"]
    if kind == "full":
        return {"left": left, "top": top, "width": w, "height": h}
    if kind == "left_half":
        return {"left": left, "top": top, "width": max(1, w // 2), "height": h}
    if kind == "right_half":
        half = w // 2
        return {"left": left + half, "top": top, "width": max(1, w - half), "height": h}
    if kind == "top_half":
        return {"left": left, "top": top, "width": w, "height": max(1, h // 2)}
    if kind == "bottom_half":
        half = h // 2
        return {"left": left, "top": top + half, "width": w, "height": max(1, h - half)}
    # 默认左半屏
    return {"left": left, "top": top, "width": max(1, w // 2), "height": h}


def _encode_capture(rgb: bytes, size: tuple[int, int], max_long_edge: int) -> dict:
    width, height = size
    original_bytes = len(rgb)
    try:
        from PIL import Image
    except ImportError:
        import mss.tools

        png = mss.tools.to_png(rgb, size)
        return {
            "mime": "image/png",
            "data": base64.b64encode(png).decode("ascii"),
            "width": width,
            "height": height,
            "original_width": width,
            "original_height": height,
            "original_bytes": original_bytes,
            "encoded_bytes": len(png),
            "compressed": False,
            "fallback": "pillow_missing",
        }

    image = Image.frombytes("RGB", size, rgb)
    original_width, original_height = image.size
    limit = max(0, int(max_long_edge or 0))
    if limit > 0:
        long_edge = max(image.size)
        if long_edge > limit:
            scale = limit / float(long_edge)
            new_size = (
                max(1, int(round(image.size[0] * scale))),
                max(1, int(round(image.size[1] * scale))),
            )
            image = image.resize(new_size, Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=88, optimize=True)
    encoded = out.getvalue()
    return {
        "mime": "image/jpeg",
        "data": base64.b64encode(encoded).decode("ascii"),
        "width": image.size[0],
        "height": image.size[1],
        "original_width": original_width,
        "original_height": original_height,
        "original_bytes": original_bytes,
        "encoded_bytes": len(encoded),
        "compressed": True,
        "fallback": "",
    }


def main() -> None:
    if not _screen_capture_allowed():
        print(
            "屏幕录制权限未开启，macOS 可能只返回桌面壁纸，无法读取其他应用的题目。"
            "请前往「系统设置 → 隐私与安全性 → 屏幕与系统音频录制」开启启动本助手的应用权限"
            "（桌面版通常为 Electron，终端启动时为 Terminal/iTerm 或 Python），然后完全退出并重新启动助手。",
            file=sys.stderr,
        )
        sys.exit(4)
    try:
        import mss
        import mss.tools
    except ImportError:
        print("mss missing", file=sys.stderr)
        sys.exit(2)
    region_kind = (sys.argv[1] or "left_half").strip() if len(sys.argv) > 1 else "left_half"
    if region_kind not in ("current_full", "full", "left_half", "right_half", "top_half", "bottom_half"):
        region_kind = "left_half"
    try:
        max_long_edge = int(sys.argv[2]) if len(sys.argv) > 2 else 1600
    except (TypeError, ValueError):
        max_long_edge = 1600
    try:
        with mss.mss() as sct:
            if len(sct.monitors) < 2:
                print("no monitor", file=sys.stderr)
                sys.exit(3)
            mon = _current_monitor(sct.monitors, _cursor_position()) if region_kind == "current_full" else sct.monitors[1]
            region = _region_for_monitor(mon, "full" if region_kind == "current_full" else region_kind)
            shot = sct.grab(region)
            payload = _encode_capture(shot.rgb, shot.size, max_long_edge)
    except Exception as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    sys.stdout.write(json.dumps(payload, separators=(",", ":")))
    sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
