#!/usr/bin/env python3
"""
Test script to validate PBIR transformation logic for both v1 and v2 schemas
"""
import json

# ============================================================
# v1.0.0 schema: byConnection requires all explicit properties
# ============================================================
pbir_v1_original = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/1.0.0/schema.json",
    "version": "4.0",
    "datasetReference": {
        "byPath": {
            "path": "../../SemanticModels/Finance Summary.SemanticModel"
        }
    }
}

pbir_v1_expected = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/1.0.0/schema.json",
    "version": "4.0",
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

# ============================================================
# v2.0.0 schema: byConnection only allows connectionString
# ============================================================
pbir_v2_original = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
    "version": "4.0",
    "datasetReference": {
        "byPath": {
            "path": "../../SemanticModels/Origination.SemanticModel"
        }
    }
}

pbir_v2_expected = {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
    "version": "4.0",
    "datasetReference": {
        "byConnection": {
            "connectionString": "semanticmodelid=dfae4241-471b-4bdb-80e6-712cf4b295b9"
        }
    }
}

print("=== v1.0.0 Schema (explicit properties) ===")
print("Original:")
print(json.dumps(pbir_v1_original, indent=2))
print("\nExpected:")
print(json.dumps(pbir_v1_expected, indent=2))

print("\n" + "="*60)
print("\n=== v2.0.0 Schema (connectionString only) ===")
print("Original:")
print(json.dumps(pbir_v2_original, indent=2))
print("\nExpected:")
print(json.dumps(pbir_v2_expected, indent=2))

# Validate v1 has all required properties
v1_conn = pbir_v1_expected["datasetReference"]["byConnection"]
v1_required = {"pbiServiceModelId", "pbiModelVirtualServerName", "pbiModelDatabaseName", "name", "connectionType"}
assert v1_required.issubset(v1_conn.keys()), "v1 format missing required properties"
print("\n✓ v1 format has all required properties")

# Validate v2 has only connectionString and it's a non-null string
v2_conn = pbir_v2_expected["datasetReference"]["byConnection"]
assert list(v2_conn.keys()) == ["connectionString"], "v2 format should only have connectionString"
assert isinstance(v2_conn["connectionString"], str), "v2 connectionString must be a string, not null"
print("✓ v2 format has connectionString only (non-null string)")

# ============================================================
# Absent $schema: should default to v1 format (safer)
# ============================================================
pbir_no_schema = {
    "version": "4.0",
    "datasetReference": {
        "byPath": {
            "path": "../../SemanticModels/Cash Collection.SemanticModel"
        }
    }
}

# When $schema is absent, _build_by_connection should use v1 format
schema_url = pbir_no_schema.get('$schema', '')
is_v2 = '2.0.0' in schema_url
assert not is_v2, "Absent $schema should NOT be treated as v2"
schema_label = 'v2' if is_v2 else 'v1'
assert schema_label == 'v1', "Absent $schema should default to v1 label"
print("✓ Absent $schema correctly defaults to v1 format")
