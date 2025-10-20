"""
Recipe parsing service using OpenAI API
"""

import os
import base64
import json
from typing import Dict, List, Optional
from openai import OpenAI
import PyPDF2


class RecipeParser:
    """Parse recipes using OpenAI API"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key or self.api_key == "your-openai-key-here":
            raise ValueError("OpenAI API key not configured. Set OPENAI_API_KEY in .env file")

        self.client = OpenAI(api_key=self.api_key)

    def encode_image(self, image_path: str) -> str:
        """Encode image to base64"""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def parse_recipe_with_ai(self, file_path: str, file_type: str) -> Dict:
        """Parse recipe using OpenAI API"""

        try:
            # Prepare the content based on file type
            if file_type == 'pdf':
                # Extract text from PDF
                with open(file_path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    text_content = ""
                    for page in pdf_reader.pages:
                        text_content += page.extract_text()

                # Use GPT-4o-mini for text-based parsing
                response = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": """You are an expert at parsing recipes.
                            Extract structured data from the recipe text provided.
                            Return a JSON object with the following structure:
                            {
                                "name": "string (recipe name)",
                                "category": "string (one of: appetizer, entree, side, dessert, beverage, sauce, prep, other)",
                                "yield_amount": number (how many servings/portions),
                                "yield_unit": "string (servings, portions, cups, etc)",
                                "prep_time": number (in minutes),
                                "cook_time": number (in minutes),
                                "instructions": "string (step-by-step cooking instructions, preserve formatting with line breaks)",
                                "ingredients": [
                                    {
                                        "description": "string (ingredient name as written in recipe)",
                                        "quantity": number,
                                        "unit": "string (cup, tbsp, lb, oz, etc)"
                                    }
                                ]
                            }

                            CRITICAL INSTRUCTIONS:
                            - Extract exact ingredient quantities and units as specified
                            - Preserve instruction formatting and steps
                            - If yield is not specified, use a reasonable estimate
                            - Convert mixed fractions to decimals (e.g., 1 1/2 = 1.5)
                            - For ingredients, separate quantity from description
                            - If any field is not found, use null or reasonable defaults

                            Examples:
                            "2 cups flour" -> {"description": "flour", "quantity": 2, "unit": "cup"}
                            "1 1/2 tsp salt" -> {"description": "salt", "quantity": 1.5, "unit": "tsp"}
                            "3 eggs" -> {"description": "eggs", "quantity": 3, "unit": "each"}
                            """
                        },
                        {
                            "role": "user",
                            "content": f"Parse this recipe:\n\n{text_content}"
                        }
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1
                )

            elif file_type in ['png', 'jpg', 'jpeg']:
                # Use Vision API for images
                base64_image = self.encode_image(file_path)

                response = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": """You are an expert at parsing recipes from images.
                            Extract structured data from the recipe image provided.
                            Return a JSON object with the following structure:
                            {
                                "name": "string (recipe name)",
                                "category": "string (one of: appetizer, entree, side, dessert, beverage, sauce, prep, other)",
                                "yield_amount": number (how many servings/portions),
                                "yield_unit": "string (servings, portions, cups, etc)",
                                "prep_time": number (in minutes),
                                "cook_time": number (in minutes),
                                "instructions": "string (step-by-step cooking instructions, preserve formatting with line breaks)",
                                "ingredients": [
                                    {
                                        "description": "string (ingredient name as written in recipe)",
                                        "quantity": number,
                                        "unit": "string (cup, tbsp, lb, oz, etc)"
                                    }
                                ]
                            }

                            CRITICAL INSTRUCTIONS:
                            - Extract exact ingredient quantities and units as specified
                            - Preserve instruction formatting and steps
                            - If yield is not specified, use a reasonable estimate
                            - Convert mixed fractions to decimals (e.g., 1 1/2 = 1.5)
                            - For ingredients, separate quantity from description
                            - If any field is not found, use null or reasonable defaults

                            Parse this recipe image and extract all recipe details including ingredients and instructions."""
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{base64_image}"
                                    }
                                }
                            ]
                        }
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1
                )

            elif file_type == 'txt':
                # Read text file
                with open(file_path, 'r', encoding='utf-8') as file:
                    text_content = file.read()

                response = self.client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {
                            "role": "system",
                            "content": """You are an expert at parsing recipes.
                            Extract structured data from the recipe text provided.
                            Return a JSON object as specified in previous instructions."""
                        },
                        {
                            "role": "user",
                            "content": f"Parse this recipe:\n\n{text_content}"
                        }
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1
                )
            else:
                raise ValueError(f"Unsupported file type: {file_type}")

            # Parse the response
            content = response.choices[0].message.content
            print(f"OpenAI Response Content: {content}")  # Debug logging
            parsed_data = json.loads(content)
            print(f"Parsed Data: {parsed_data}")  # Debug logging

            return {
                "success": True,
                "data": parsed_data
            }

        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"Failed to parse AI response as JSON: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Recipe parsing failed: {str(e)}"
            }
