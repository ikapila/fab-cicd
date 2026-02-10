#!/usr/bin/env python3
"""
Test script to validate PBIR transformation logic
"""
import json

# Sample PBIR content with byPath reference
pbir_original = {
    "datasetReference": {
        "byPath": {
            "path": "../../Semanticmodels/Finance Summary.SemanticModel"
        }
    },
    "config": {
        "version": "5.49",
        "themeCollection": {
            "baseTheme": {
                "name": "CY24SU06"
            }
        }
    }
}

# Expected transformation with byConnection
pbir_expected = {
    "datasetReference": {
        "byConnection": {
            "connectionString": None,
            "pbiServiceModelId": None,
            "pbiModelVirtualServerName": "sobe_wowvirtualserver",
            "pbiModelDatabaseName": "dfae4241-471b-4bdb-80e6-712cf4b295b9",
            "name": "EntityDataSource",
            "connectionType": "pbiServiceXmlaStyleLive"
        }
    },
    "config": {
        "version": "5.49",
        "themeCollection": {
            "baseTheme": {
                "name": "CY24SU06"
            }
        }
    }
}

print("Original PBIR:")
print(json.dumps(pbir_original, indent=2))
print("\n" + "="*60 + "\n")
print("Expected transformed PBIR:")
print(json.dumps(pbir_expected, indent=2))
