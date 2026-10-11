from pathlib import Path
from PIL import Image,ImageDraw
from luminal_images import ROOT,submit
source=ROOT/'assets/2d/reference.png';im=Image.open(source);mask=Image.new('L',im.size,255);d=ImageDraw.Draw(mask)
d.polygon([(511,158),(592,165),(602,222),(567,274),(543,354),(480,427),(433,432),(392,387),(395,315),(425,243),(470,211),(500,192)],fill=0)
mask.save(ROOT/'assets/2d/clean_mask.png')
submit('clean_plate',source,'Remove ONLY the young man lying on this bed, leaving a completely EMPTY bed. Restore the rumpled blue-gray and mauve blanket, pillow and mattress in the areas formerly covered by his body, matching the existing detailed hand-drawn anime linework and painted shadow lighting. No person, no body parts, no duplicate furniture. Keep every unmasked pixel and the same room, perspective, lamp, headboard, window, desk, chair, posters and closed door unchanged. This is an empty background plate for a 2D anime animation.',ROOT/'assets/2d/clean_mask.png',quality='high')
