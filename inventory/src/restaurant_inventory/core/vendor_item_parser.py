"""
Vendor item list parser for CSV and Excel files
"""

import os
import csv
import io
import re
from typing import Dict, List, Optional, Tuple
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

    @staticmethod
    def parse_unit_size(unit_size_str: str) -> Tuple[Optional[float], Optional[str]]:
        """
        Parse a combined unit size string into numeric size and unit.

        Examples:
            "5.0 LB" -> (5.0, "LB")
            "10.0 LB" -> (10.0, "LB")
            "16.0 OZ" -> (16.0, "OZ")
            "2.5 GAL" -> (2.5, "GAL")
            "54.0 CO" -> (54.0, "CO")  # Count
            "32.0 FOZ" -> (32.0, "FOZ")  # Fluid Ounces

        Args:
            unit_size_str: String like "5.0 LB" or "16.0 OZ"

        Returns:
            Tuple of (numeric_size, unit) or (None, None) if parsing fails
        """
        if not unit_size_str or pd.isna(unit_size_str):
            return None, None

        try:
            # Convert to string and clean up
            unit_str = str(unit_size_str).strip()

            # Pattern: number (with optional decimal) followed by space and unit
            # Examples: "5.0 LB", "10 LB", "16.0 OZ", "2.5 GAL"
            match = re.match(r'^(\d+\.?\d*)\s+([A-Za-z]+)$', unit_str)

            if match:
                size = float(match.group(1))
                unit = match.group(2).upper()
                return size, unit

            return None, None

        except (ValueError, AttributeError):
            return None, None

    def post_process_items(self, items: List[Dict], parse_unit_size_field: Optional[str] = None) -> List[Dict]:
        """
        Post-process items to handle vendor-specific formats.

        Args:
            items: List of parsed items
            parse_unit_size_field: If provided, parse this field as combined unit size

        Returns:
            Processed items with pack_size and unit separated
        """
        if not parse_unit_size_field:
            return items

        processed_items = []
        for item in items:
            # Copy the item
            processed_item = item.copy()

            # If the item has the combined unit size field, parse it
            if parse_unit_size_field in processed_item:
                unit_size_value = processed_item.get(parse_unit_size_field)
                size, unit = self.parse_unit_size(unit_size_value)

                if size is not None:
                    processed_item['pack_size'] = size
                if unit is not None:
                    processed_item['unit'] = unit

            processed_items.append(processed_item)

        return processed_items
