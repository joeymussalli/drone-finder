# Sim Demo Photo Credits

All photos are from Wikimedia Commons, reused under the licenses listed below.
Each entry gives the local filename, the item it represents (if any), the
author, the license, and the Commons source page. Detection was verified with
YOLO-World (yolov8m-worldv2).

## Item photos

| Local file | Item | Author | License | Source |
|---|---|---|---|---|
| item_water_bottle.jpg | water bottle | Kykywinks | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:Plastic_Water_Bottle.jpg |
| item_backpack.jpg | backpack | Viktor Pinchuk | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:Backpack_small.jpg |
| item_coffee_mug.jpg | coffee mug | Ryan Holloway (Unsplash) | CC0 | https://commons.wikimedia.org/wiki/File:Coffee_Mug_(Unsplash).jpg |
| item_laptop.jpg | laptop | Norbert Levajsics (Unsplash) | CC0 | https://commons.wikimedia.org/wiki/File:Laptop_on_a_neat_desk_(Unsplash).jpg |
| item_cell_phone.jpg | cell phone | Sertion | CC BY-SA 3.0 | https://commons.wikimedia.org/wiki/File:I7500_with_screen_protector.jpg |

## Plain room photos

| Local file | Author | License | Source |
|---|---|---|---|
| plain_room_1.jpg | aismallard | CC BY-SA 3.0 | https://commons.wikimedia.org/wiki/File:Empty_apartment_room_with_corner_windows.jpg |
| plain_room_2.jpg | aismallard | CC BY-SA 3.0 | https://commons.wikimedia.org/wiki/File:Empty_apartment_room_with_extension_cord.jpg |
| plain_room_3.jpg | Acabashi | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:Copped_Hall_housekeeper%27s_room,_Epping,_Essex,_England.jpg |

## Licenses

- CC0: public-domain dedication, no attribution required (credited anyway).
- CC BY-SA 3.0: https://creativecommons.org/licenses/by-sa/3.0/
- CC BY-SA 4.0: https://creativecommons.org/licenses/by-sa/4.0/

Images were downloaded at ~640 px width via the Wikimedia Special:FilePath
endpoint and are unmodified except for scaling.

## Grid layout (sim_layout.json)

Items sit in rows 3-6 of the 7x7 grid (default 3x3 m area, 0.5 m step), so every
search runs well into the sweep before the find:

- water bottle -> cell (1, 3)
- backpack     -> cell (5, 3)
- coffee mug   -> cell (3, 4)
- laptop       -> cell (1, 6)
- cell phone   -> cell (5, 6)

Every other cell shows a plain room photo. Search for an item by name and the
drone finds it at its cell.
