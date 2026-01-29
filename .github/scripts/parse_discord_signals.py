#!/usr/bin/env python3
import json
import os

# Create a simple summary embed (no detailed signal fields - those will be sent as chart images)
payload = {
    "embeds": [{
        "title": os.environ['TITLE'],
        "description": os.environ['DESCRIPTION'].replace('\\n', '\n'),
        "color": int(os.environ['COLOR']),
        "footer": {"text": "Harmonic Pattern Scanner | Charts will follow..."},
        "timestamp": os.environ['TIMESTAMP']
    }]
}

print(json.dumps(payload))
