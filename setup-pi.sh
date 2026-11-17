#!/usr/bin/env bash
# Turns a Raspberry Pi (Raspberry Pi OS Bookworm or newer) into a
# standalone wifi hotspot that sends every visitor to the portal page.
#
# Usage, from inside the portal folder on the Pi:
#   sudo ./setup-pi.sh                       open network (no password)
#   sudo ./setup-pi.sh "magnetronbar"        WPA2 network with that password
#
# The network name comes from chapter.json ("ssid").
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then echo "Run with sudo."; exit 1; fi

DIR="$(cd "$(dirname "$0")" && pwd)"
SSID="$(python3 -c 'import json;print(json.load(open("'"$DIR"'/chapter.json"))["ssid"])')"
IP="$(python3 -c 'import json;print(json.load(open("'"$DIR"'/chapter.json"))["server_ip"])')"
PASSWORD="${1:-}"
CON="portal"

echo "Setting up network '$SSID' on $IP"

# 1. Make sure wifi is allowed to transmit (the country must be set once,
#    e.g. with: sudo raspi-config nonint do_wifi_country NL)
rfkill unblock wifi || true

# 2. Create the hotspot with NetworkManager.
#    "shared" mode makes NetworkManager hand out addresses (DHCP) and DNS.
nmcli connection delete "$CON" >/dev/null 2>&1 || true
nmcli connection add type wifi ifname wlan0 con-name "$CON" autoconnect yes ssid "$SSID" \
  802-11-wireless.mode ap 802-11-wireless.band bg 802-11-wireless.channel 6 \
  ipv4.method shared ipv4.addresses "$IP/24" ipv6.method disabled

if [ -n "$PASSWORD" ]; then
  nmcli connection modify "$CON" wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$PASSWORD" \
    wifi-sec.proto rsn wifi-sec.pairwise ccmp wifi-sec.group ccmp
fi

# 3. Answer every DNS lookup with the Pi's own address.
#    This is what makes it a captive portal: whatever site a phone asks
#    for, it lands on our server.
mkdir -p /etc/NetworkManager/dnsmasq-shared.d
cat > /etc/NetworkManager/dnsmasq-shared.d/portal.conf <<EOF
address=/#/$IP
# DHCP option 114 (RFC 8910): tells newer phones where the portal is
dhcp-option=114,http://$IP/
EOF

# 4. Run the portal server at boot.
cat > /etc/systemd/system/portal.service <<EOF
[Unit]
Description=Roodkapje chapter portal
After=network-online.target

[Service]
WorkingDirectory=$DIR
ExecStart=/usr/bin/python3 $DIR/server.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now portal.service
nmcli connection up "$CON"

echo
echo "Done. Join '$SSID' with a phone; the portal page should open."
echo "Logs:  journalctl -u portal -f"
