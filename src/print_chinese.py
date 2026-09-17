import os
from rich.console import Console

from PIL import Image, ImageDraw, ImageFont


def print_big_chinese(text, size=16):
    # 1. Dynamically target the built-in Windows Chinese Font (Microsoft YaHei)
    font_path = os.path.join(os.environ["WINDIR"], "Fonts", "msyh.ttc")

    # 2. Create an empty black canvas based on text length
    img = Image.new("1", (len(text) * size, size + 2), color=0)
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype(font_path, size)
    except IOError:
        print("Could not load Windows Chinese font.")
        return

    # 3. Draw white text onto the canvas
    draw.text((0, 0), text, fill=1, font=font)

    # 4. Read pixels and map to terminal block characters
    for y in range(img.height):
        row = ""
        for x in range(img.width):
            row += "██" if img.getpixel((x, y)) else "  "

        if row.strip():  # Skip empty whitespace lines
            print(row)

def print_highlight_chinese (text):
    console = Console()
    os.system("chcp 65001 > nul")

    # Draw a continuous line breaker
    console.print("=" * 40, style="bold red")
    console.print(text, style="bold white on yellow")
    #console.print(text, style="bold white on yellow")
    #console.print(text, style="bold white on yellow")
    console.print("=" * 40, style="bold red")

    #console.print("\nAction: If qcom does not go up today, sell qcom option; sell tsla put; sell qqq call, \n", style="bold white on yellow")
    #console.print("\nAction: sell put glw at 140, \n", style="bold white on yellow")
        
if __name__ == "__main__":
    print_highlight_chinese(" 遵 守 交 易 纪 律")