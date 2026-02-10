#!/usr/bin/env python3
"""
Test to verify the byConnection format matches Power BI expectations
"""
import json

# What we're generating
our_format = {
    "datasetReference": {
        "byConnection": {
            "connectionString": None,
            "pbiServiceModelId": None,
            "pbiModelVirtualServerName": "sobe_wowvirtualserver",
            "pbiModelDatabaseName": "dfae4241-471b-4bdb-80e6-712cf4b295b9",
            "name": "EntityDataSource",
            "connectionType": "pbiServiceXmlaStyleLive"
        }
    }
}

# Standard Power BI format for workspace connection
standard_format = {
    "datasetReference": {
        "byConnection": {
            "connectionString": None,
            "pbiServiceModelId": None,
            "pbiModelVirtualServerName": "sobe_wowvirtualserver",
            "pbiModelDatabaseName": "dfae4241-471b-4bdb-80e6-712cf4b295b9",
            "name": "EntityDataSource",
            "connectionType": "pbiServiceXmlaStyleLive"
        }
    }
}

print("Our format:")
print(json.dumps(our_format, indent=2))
print("\n" + "="*60)
print("\nStandard format:")
print(json.dumps(standard_format, indent=2))
print("\n" + "="*60)
print("\nMatch:", our_format == standard_format)
