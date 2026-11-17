# Roodkapje chapter portal

One folder = one chapter = one wifi network.

When a phone joins the network, it opens a short entry screen (network name,
lease time, an "enter" button). The button leads into your own interface in `site/`.

## Files

- `chapter.json`: network name, intro text, lease length, button label (`enter_label`, optional)
- `site/`: your interface. Put your `index.html` here with all its css, js, images,
  video and fonts. Subfolders are fine.
- `server.py`: the portal (Python standard library only)
- `setup-pi.sh`: turns a Raspberry Pi into the hotspot
- `data/`: created automatically; holds leases and the guestbook

## Try it on your laptop

    Mac/Linux:   PORT=8080 python3 server.py
    Windows:     $env:PORT=8080
                 python server.py

Open http://localhost:8080. Delete the `data` folder to reset your timer.

## Rules for your interface in site/

- **Everything must be local.** There is no internet on the network: no Google Fonts,
  no CDN libraries, no YouTube/Vimeo embeds. Download fonts and scripts into `site/`.
- **Use relative paths**, e.g. `media/meent_01.jpg`, not `/media/...` or `C:\...`.
- The page is served at `/site/`, so `site/index.html` is the start page.
- When the lease runs out, every request to `/site/` sends the player back to the
  entry screen, which then says "lease expired".

## Kapsalons (extra time)

Hide codes along the route. Each valid code adds time to the player's lease.
Set them in `chapter.json`:

    "kapsalons": ["KNIP", "FOHN", "SCHAAR"],
    "kapsalon_minutes": 5,
    "kapsalon_revives": true

- Codes are not case-sensitive, and spaces are ignored.
- Each code works once per phone, per chapter (per Pi).
- `kapsalon_revives: true` lets a code reopen an expired lease (restarting with 5 minutes).
  Set it to `false` if expired should stay expired.
- After 5 wrong codes, a phone has to wait 60 seconds, so codes can't be guessed quickly.
- The entry screen has a code field. Your own interface can use `POST /kapsalon` (below).

## Optional: things your interface can ask the server

- `GET /lease` returns `{"remaining": 1742, "ssid": "...", "chapter": "02", "title": "Meent"}`.
  Use it to show the timer in your own design. `site/index.html` has an example.
- `POST /kapsalon` with JSON `{"code": "KNIP"}` returns
  `{"ok": true, "message": "lease renewed +5:00", "remaining": 2099}`.
  `site/index.html` has a working example.
- `GET /guestbook` returns all entries.
- `POST /guestbook` with JSON `{"name": "...", "text": "..."}` adds one.

## Preparing media

- **Video:** MP4 with H.264 video and AAC audio, 720p, ideally under ~50 MB per clip.
  Avoid iPhone .mov/HEVC files: many Android phones can't play them.
  Convert with HandBrake (free): preset "Fast 720p30", and tick "Web Optimized".
  In your HTML use `<video controls playsinline preload="metadata">`.
- **Photos:** JPG or WebP, about 1600 px on the long side. Convert iPhone HEIC photos to JPG.
- **Audio:** MP3 or M4A.

## Put it on a Raspberry Pi

Any Pi with wifi (Zero 2 W, 3A+, 3B+, 4, 5) running Raspberry Pi OS Bookworm.

1. Flash Raspberry Pi OS Lite with Raspberry Pi Imager. Set wifi country NL and enable SSH.
2. Copy this folder to the Pi: `scp -r portal pi@<pi-address>:~`
3. On the Pi:

       cd ~/portal
       sudo nohup ./setup-pi.sh > setup.log 2>&1 &                 # open network
       sudo nohup ./setup-pi.sh magnetronbar > setup.log 2>&1 &    # or with a password

The Pi leaves your home wifi when the hotspot starts, so your SSH session drops.
Join the new network and reconnect with `ssh pi@10.0.0.1`.

To undo: `sudo nmcli connection delete portal && sudo systemctl disable --now portal`

## Things to know

- Phones open portal pages in a small sandboxed browser that forgets everything when
  it closes. The entry screen tells players to open `10.0.0.1` in their normal browser.
- Some phones leave networks without internet. Players should tap "stay connected"
  or "use without internet".
- The lease is tracked per IP address, so it's a game timer, not real security.
- Wifi range is roughly 10–30 m, less through walls and in crowds.
