# Sim Demo Photo Credits

All photos below are from Wikimedia Commons and are reused under their listed
licenses. Each entry lists the local filename, the item it represents (if any),
the author, the license, and the Commons source page.

## Item photos

| Local file | Item | Author | License | Source |
|---|---|---|---|---|
| item_water_bottle.jpg | water bottle | Kykywinks | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:Plastic_Water_Bottle.jpg |
| item_backpack.jpg | backpack | Viktor Pinchuk | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:Backpack_small.jpg |
| item_laptop.jpg | laptop | Norbert Levajsics (Unsplash) | CC0 | https://commons.wikimedia.org/wiki/File:Laptop_on_a_neat_desk_(Unsplash).jpg |
| item_coffee_mug.jpg | coffee mug | PedanticNarrativeController | CC0 | https://commons.wikimedia.org/wiki/File:Coffee_steaming_in_a_mug.jpg |
| item_keys.jpg | keys | Shixart1985 | CC BY 2.0 | https://commons.wikimedia.org/wiki/File:A_hand_holds_a_set_of_keys.jpg |

## Plain room photos

| Local file | Author | License | Source |
|---|---|---|---|
| plain_room_1.jpg | aismallard | CC BY-SA 3.0 | https://commons.wikimedia.org/wiki/File:Empty_apartment_room_with_corner_windows.jpg |
| plain_room_2.jpg | aismallard | CC BY-SA 3.0 | https://commons.wikimedia.org/wiki/File:Empty_apartment_room_with_extension_cord.jpg |
| plain_room_3.jpg | Acabashi | CC BY-SA 4.0 | https://commons.wikimedia.org/wiki/File:Copped_Hall_housekeeper%27s_room,_Epping,_Essex,_England.jpg |

## Licenses

- CC0: public-domain dedication, no attribution required (credited anyway).
- CC BY 2.0: https://creativecommons.org/licenses/by/2.0/
- CC BY-SA 3.0: https://creativecommons.org/licenses/by-sa/3.0/
- CC BY-SA 4.0: https://creativecommons.org/licenses/by-sa/4.0/

Images were downloaded at ~640 px width via the Wikimedia Special:FilePath
endpoint and are unmodified except for scaling.

## Grid layout (sim_layout.json)

Items are placed at fixed cells on the 7x7 grid (default 3x3 m area, 0.5 m step):

- water bottle -> cell (1, 1)
- backpack     -> cell (5, 1)
- laptop       -> cell (3, 3)
- keys         -> cell (1, 5)
- coffee mug   -> cell (5, 5)

Every other cell shows a plain room photo. Search for an item by name and the
drone will "find" it at its cell.
