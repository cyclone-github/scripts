#!/usr/bin/env python3

import argparse
import requests
import json
import sys
from collections import Counter
from datetime import datetime

"""
IP Geolocation Lookup Tool

This script reads a list of IP addresses and performs geolocation lookups for each IP
It supports the optional use of an API key for enhanced rate limits if needed
In addition to python3, this script requires "requests", install by running "pip3 install requests"

written by cyclone
"""

# lookup IP info
def get_ip_details(ip, api_key):
    if ip not in ip_details:
        url = "http://ipinfo.io/{}/json".format(ip)
        if api_key:
            url += "?token=" + api_key  # append API key if provided
        response = requests.get(url)
        data = json.loads(response.text)
        ip_details[ip] = data
    else:
        data = ip_details[ip]
    return data

parser = argparse.ArgumentParser(description="IP Geolocation Lookup Tool")
parser.add_argument("input_file", help="File containing a list of IP addresses")
parser.add_argument("--api", help="API key for enhanced rate limits (optional)", dest="api_key")
args = parser.parse_args()

try:
    with open(args.input_file, 'r') as f:
        ips = f.read().splitlines()
except FileNotFoundError:
    print("Error: File {} not found.".format(args.input_file))
    sys.exit(1)

unique_ips = list(set(ips))
total_ips = len(ips)
unique_ip_count = len(unique_ips)

country_count = Counter()

ip_details = {}

for i, ip in enumerate(unique_ips, 1):
    data = get_ip_details(ip, args.api_key)
    sys.stdout.write(f"\rTotal IPs Processed: {i}/{unique_ip_count}")
    sys.stdout.flush()

    country = data.get("country", "Unknown")
    country_count[country] += 1

sys.stdout.write("\n")

# print stats
print(f"\nTotal IPs: {total_ips}")
print(f"Unique IPs: {unique_ip_count}")
print("Most Common Countries:")
for country, count in country_count.most_common():
    print(f"{count} {country}")

output_filename = f"ip_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

# save results to file
with open(output_filename, 'w') as output_file:
    output_file.write(f"Total IPs: {total_ips}\n")
    output_file.write(f"Unique IPs: {unique_ip_count}\n")
    output_file.write("\nMost Common Countries:\n")
    for country, count in country_count.most_common():
        output_file.write(f"{count} {country}\n")
    output_file.write("\nIP Details:\n")
    for ip, data in ip_details.items():
        output_file.write(json.dumps(data, indent=2) + "\n")

print(f"Output saved to {output_filename}")