"""
take_screenshot skill — 通过 screen-capture MCP 截屏。
"""


def run(ctx, region="full"):
    ctx.log(f"taking screenshot region={region}")
    result = ctx.mcp("screen-capture").capture(region=region)
    if not isinstance(result, dict):
        result = {}
    return {
        "image_path": result.get("path", ""),
        "width": result.get("width", 0),
        "height": result.get("height", 0),
    }
