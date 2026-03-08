#!/usr/bin/env python3
"""
Test to verify byConnection format for both v1 and v2 PBIR schemas
"""
import json

# v1.0.0 schema format (explicit properties)
v1_format = {
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

# v2.0.0 schema format (connectionString only, must be a non-null string)
v2_format = {
    "datasetReference": {
        "byConnection": {
            "connectionString": "semanticmodelid=dfae4241-471b-4bdb-80e6-712cf4b295b9"
        }
    }
}

print("v1.0.0 schema format:")
print(json.dumps(v1_format, indent=2))
print("\n" + "="*60)
print("\nv2.0.0 schema format:")
print(json.dumps(v2_format, indent=2))
print("\n" + "="*60)

# Validate v1
v1_conn = v1_format["datasetReference"]["byConnection"]
v1_keys = {"pbiServiceModelId", "pbiModelVirtualServerName", "pbiModelDatabaseName", "name", "connectionType"}
assert v1_keys.issubset(v1_conn.keys()), "v1 missing required keys"

# Validate v2
v2_conn = v2_format["datasetReference"]["byConnection"]
assert "connectionString" in v2_conn, "v2 missing connectionString"
assert isinstance(v2_conn["connectionString"], str), "v2 connectionString must be string"
assert len(v2_conn) == 1, "v2 should only have connectionString"

print("\n✓ Both formats valid")
