import sys
from PIL import Image, ImageDraw, ImageFont

img = Image.new("RGBA", (1920, 1080), (10, 14, 26, 255))
draw = ImageDraw.Draw(img)

# Try font
font_paths = [
    "/System/Library/Fonts/HelveticaNeue.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]
font = None
for p in font_paths:
    try:
        font = ImageFont.truetype(p, 48)
        print("Loaded font:", p)
        break
    except Exception as e:
        pass

if font is None:
    font = ImageFont.load_default()
    print("Using default font")

draw.text((100, 100), "code-anime // STUDIO IN CODE", fill=(245, 238, 220, 255), font=font)
img.save("output/demo90/test_frame.png")
print("Saved test_frame.png successfully")
