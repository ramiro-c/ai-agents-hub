"""

Product extraction agent with structured JSON output.

Demonstrates ADK's output_schema with Pydantic BaseModel.

"""

from google.adk.agents import LlmAgent
from pydantic import BaseModel, Field

# Step 1: Define the output structure with Pydantic


class ProductInfo(BaseModel):
    product_name: str = Field(description="The full name of the product")

    price: float = Field(description="The price in USD")

    storage: str = Field(description="Storage capacity (e.g., '256GB')")

    color: str = Field(
        default="Not specified", description="Product color if mentioned"
    )


# Step 2: Create agent with output_schema

root_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="product_extractor",
    description=(
        "Extracts product information from user messages and returns structured JSON"
    ),
    instruction="""You are a Product Information Extractor.

Your task:

- Read the user's message about a product

- Extract: product_name, price, storage, and color (if mentioned)

- Respond ONLY with valid JSON matching this format:


  "product_name": "product name here",

  "price": 999.99,

  "storage": "256GB",

  "color": "Space Black"

}


Rules:

- price must be a number (no dollar signs)

- storage must include unit (GB, TB)

- If color not mentioned, use "Not specified"

- Output ONLY the JSON, no explanation text""",
    output_schema=ProductInfo,  # Enforce this exact structure
    output_key="extracted_product",  # Store result in session state
)
