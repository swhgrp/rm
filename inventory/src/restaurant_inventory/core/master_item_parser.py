"""
Master item list parser for CSV and Excel files
"""

import os
import csv
import io
from typing import Dict, List, Optional
import pandas as pd


class MasterItemParser:
    """Parse master item lists from CSV or Excel files"""

    def __init__(self):
        self.supported_extensions = {'.csv', '.xlsx', '.xls'}

    def parse_file(self, file_path: str, file_type: str, column_mapping: Optional[Dict[str, str]] = None) -> Dict:
        """
        Parse master item file

        Args:
            file_path: Path to the uploaded file
            file_type: File extension (csv, xlsx, xls)
            column_mapping: Optional mapping of file columns to our fields
                           e.g., {"Item Name": "name", "UOM": "unit_of_measure"}

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
            for idx, row in df.iterrows():
                item = {}

                # Map file columns to our fields
                for file_col, our_field in column_mapping.items():
                    if file_col in row:
                        value = row[file_col]
                        # Handle NaN values
                        if pd.isna(value):
                            value = None
                        item[our_field] = value

                # Add row number for error reporting
                item['_row_number'] = idx + 2  # +2 for header and 0-indexing

                items.append(item)

            return {
                "success": True,
                "data": {
                    "items": items,
                    "total": len(items)
                }
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    def get_suggested_mapping(self, columns: List[str]) -> Dict[str, str]:
        """
        Suggest mapping from vendor column names to our field names

        Args:
            columns: List of column names from uploaded file

        Returns:
            Dict mapping vendor columns to our fields
        """
        # Our field names
        our_fields = {
            'name': ['name', 'item name', 'item_name', 'product', 'product name', 'description', 'item'],
            'item_code': ['item code', 'item_code', 'sku', 'code', 'item #', 'item#', 'product code'],
            'description': ['description', 'desc', 'details', 'notes'],
            'category': ['category', 'cat', 'type', 'group', 'item type'],
            'unit_of_measure': ['unit', 'uom', 'unit of measure', 'unit_of_measure', 'measure', 'base unit'],
            'secondary_unit': ['secondary unit', 'secondary_unit', 'case unit', 'pack unit', 'order unit'],
            'conversion_factor': ['conversion', 'conversion factor', 'conversion_factor', 'factor', 'pack size', 'qty per case', 'units per case'],
            'par_level': ['par', 'par level', 'par_level', 'minimum', 'min qty', 'min stock'],
        }

        suggested = {}

        for col in columns:
            col_lower = col.lower().strip()

            # Try to match to our fields
            for our_field, aliases in our_fields.items():
                for alias in aliases:
                    if col_lower == alias.lower() or alias.lower() in col_lower:
                        suggested[col] = our_field
                        break
                if col in suggested:
                    break

        return suggested

    def validate_item(self, item: Dict) -> Dict:
        """
        Validate a parsed item

        Args:
            item: Parsed item dictionary

        Returns:
            {
                "valid": bool,
                "errors": List[str]
            }
        """
        errors = []

        # Required fields
        if not item.get('name'):
            errors.append("Name is required")

        # Unit is optional - can be added later
        # Category is optional - will default to "Uncategorized"

        # Validate numeric fields
        numeric_fields = ['conversion_factor', 'par_level']
        for field in numeric_fields:
            value = item.get(field)
            if value is not None and value != '':
                try:
                    float(value)
                except (ValueError, TypeError):
                    errors.append(f"{field} must be a number")

        return {
            "valid": len(errors) == 0,
            "errors": errors
        }
