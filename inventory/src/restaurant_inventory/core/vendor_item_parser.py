"""
Vendor item list parser for CSV and Excel files
"""

import os
import csv
import io
from typing import Dict, List, Optional
import pandas as pd


class VendorItemParser:
    """Parse vendor item lists from CSV or Excel files"""

    def __init__(self):
        self.supported_extensions = {'.csv', '.xlsx', '.xls'}

    def parse_file(self, file_path: str, file_type: str, column_mapping: Optional[Dict[str, str]] = None) -> Dict:
        """
        Parse vendor item file

        Args:
            file_path: Path to the uploaded file
            file_type: File extension (csv, xlsx, xls)
            column_mapping: Optional mapping of vendor columns to our fields
                           e.g., {"Item Code": "vendor_item_code", "Description": "name"}

        Returns:
            {
                "success": bool,
                "data": {
                    "columns": [...],  # Available columns in file
                    "items": [...]     # Parsed items
                },
                "error": str (if failed)
            }
        """
        try:
            # Read file into DataFrame
            if file_type == 'csv':
                df = pd.read_csv(file_path)
            elif file_type in ['xlsx', 'xls']:
                df = pd.read_excel(file_path)
            else:
                return {
                    "success": False,
                    "error": f"Unsupported file type: {file_type}"
                }

            # Get column names
            columns = df.columns.tolist()

            # If no mapping provided, return columns for user to map
            if not column_mapping:
                # Convert sample rows and replace NaN with None for JSON serialization
                sample_df = df.head(5).fillna('')
                sample_rows = sample_df.to_dict('records')
                return {
                    "success": True,
                    "data": {
                        "columns": columns,
                        "sample_rows": sample_rows,
                        "total_rows": len(df)
                    }
                }

            # Parse items using the mapping
            items = []
            for _, row in df.iterrows():
                item = {}

                # Map vendor columns to our fields
                for vendor_col, our_field in column_mapping.items():
                    if vendor_col in row:
                        value = row[vendor_col]
                        # Handle NaN values
                        if pd.isna(value):
                            value = None
                        item[our_field] = value

                # Only add items that have at least a name or item code
                if item.get('name') or item.get('vendor_item_code'):
                    items.append(item)

            return {
                "success": True,
                "data": {
                    "columns": columns,
                    "items": items,
                    "total_rows": len(items)
                }
            }

        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to parse vendor file: {str(e)}"
            }

    def get_suggested_mapping(self, columns: List[str]) -> Dict[str, str]:
        """
        Suggest column mapping based on common vendor formats

        Args:
            columns: List of column names from the vendor file

        Returns:
            Dictionary mapping vendor columns to our fields
        """
        mapping = {}

        # Common patterns for each field
        patterns = {
            'vendor_item_code': ['item code', 'item #', 'item number', 'product code', 'sku', 'code'],
            'name': ['description', 'item description', 'product name', 'name', 'item name'],
            'pack_size': ['pack', 'pack size', 'size', 'unit size', 'package size'],
            'unit_cost': ['cost', 'unit cost', 'price', 'unit price', 'case price'],
            'category': ['category', 'dept', 'department', 'group'],
            'unit': ['unit', 'uom', 'unit of measure', 'um'],
        }

        # Match columns to fields (case-insensitive)
        for col in columns:
            col_lower = col.lower().strip()
            for field, field_patterns in patterns.items():
                if any(pattern in col_lower for pattern in field_patterns):
                    mapping[col] = field
                    break

        return mapping
