# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Order Food Workflow

This workflow integrates with the MealMe API to:
1. Search for products (e.g., coffee, food items)
2. Create a shopping cart
3. Add items to the cart
4. Create an order
5. Retrieve a checkout link for payment

The workflow takes parameters like product query, address, and customer info,
then orchestrates all the API calls needed to complete a food order.
"""

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# MealMe API Configuration
MEALME_BASE_URL = "https://api.satsuma.ai"
MEALME_API_KEY = os.getenv("MEALME_API_KEY")


def run(params: dict[str, Any]) -> dict[str, Any]:
    """
    Execute the order_food workflow.

    This function takes parameters and runs through the complete order flow:
    - Geocodes the address to get coordinates
    - Searches for products near those coordinates
    - Creates a cart
    - Adds the selected product to the cart
    - Creates an order with customer details
    - Gets a payment link for checkout

    Args:
        params: Dictionary containing:
            - query: Product search term (e.g., "coffee", "Cold Brew")
            - address: Delivery address (optional if latitude/longitude provided)
            - latitude: Latitude coordinate (optional if address provided)
            - longitude: Longitude coordinate (optional if address provided)
            - customer: Customer information dict with:
                - name: Customer name
                - email: Customer email
                - phone_number: Customer phone number
                - address: Full address dict with street_address, city, region, postal_code, country
            - dropoff_instructions: Optional delivery instructions
            - quantity: Quantity of product to order (default: 1)

    Returns:
        Dictionary with:
            - status: "success" or "error"
            - order_id: The created order ID
            - product: The product name that was ordered
            - checkout_url: The Stripe checkout link for payment
            - error: Error message if status is "error"
    """
    # Validate API key is configured
    if not MEALME_API_KEY:
        logger.error("MEALME_API_KEY environment variable is not set")
        return {
            "status": "error",
            "error": "MEALME_API_KEY environment variable is not configured",
        }

    # Extract parameters with defaults
    query = params.get("query", "")
    address = params.get("address")
    latitude = params.get("latitude")
    longitude = params.get("longitude")
    customer = params.get("customer", {})
    dropoff_instructions = params.get("dropoff_instructions", "")
    quantity = params.get("quantity", 1)

    # Validate required parameters
    if not query:
        return {"status": "error", "error": "Missing required parameter: query"}

    if not customer:
        return {"status": "error", "error": "Missing required parameter: customer"}

    # Create HTTP client with authentication
    headers = {
        "Authorization": MEALME_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        # Step 1: Geocode address if needed
        # If we have an address but no coordinates, geocode it first
        if address and (not latitude or not longitude):
            logger.info(f"Geocoding address: {address}")
            with httpx.Client() as client:
                geocode_response = client.get(
                    f"{MEALME_BASE_URL}/utility/geocode",
                    params={"address": address},
                    headers=headers,
                    timeout=30.0,
                )
                geocode_response.raise_for_status()
                geocode_data = geocode_response.json()

                # Extract coordinates from geocode response
                # Note: GeoJSON format uses [longitude, latitude] order
                # Reference: https://datatracker.ietf.org/doc/html/rfc7946#section-3.1.1
                if "data" in geocode_data and "coordinates" in geocode_data["data"]:
                    coordinates = geocode_data["data"]["coordinates"]
                    if not isinstance(coordinates, list) or len(coordinates) < 2:
                        return {
                            "status": "error",
                            "error": "Invalid coordinates format in geocode response",
                        }
                    # GeoJSON format: [longitude, latitude]
                    longitude = float(coordinates[0])
                    latitude = float(coordinates[1])
                    logger.info(
                        f"Geocoded coordinates: lat={latitude}, lon={longitude}"
                    )
                else:
                    return {
                        "status": "error",
                        "error": "Failed to geocode address: invalid response format",
                    }

        # Validate we have coordinates for product search
        if not latitude or not longitude:
            return {
                "status": "error",
                "error": "Missing coordinates. Provide either 'address' or both 'latitude' and 'longitude'",
            }

        # Step 2: Search for products
        logger.info(f"Searching for products with query: {query}")
        with httpx.Client() as client:
            product_response = client.get(
                f"{MEALME_BASE_URL}/product",
                params={"query": query, "latitude": latitude, "longitude": longitude},
                headers=headers,
                timeout=30.0,
            )
            product_response.raise_for_status()
            products = product_response.json()

            if not products or len(products) == 0:
                return {
                    "status": "error",
                    "error": f"No products found for query: {query}",
                }

            # Select the first product
            selected_product = products[0]
            product_id = selected_product["id"]
            product_name = selected_product.get("name", query)
            location_id = selected_product.get("locationId")

            logger.info(f"Selected product: {product_name} (ID: {product_id})")

            if not location_id:
                return {
                    "status": "error",
                    "error": "Product missing locationId",
                }

        # Step 3: Create cart
        logger.info(f"Creating cart for location: {location_id}")
        with httpx.Client() as client:
            cart_response = client.post(
                f"{MEALME_BASE_URL}/cart",
                json={
                    "location_id": location_id,
                    "user_id": customer.get("name", "pailflow_user"),
                    "status": "Active",
                },
                headers=headers,
                timeout=30.0,
            )
            cart_response.raise_for_status()
            cart_data = cart_response.json()
            cart_id = cart_data["id"]
            logger.info(f"Created cart: {cart_id}")

        # Step 4: Add item to cart
        logger.info(f"Adding product {product_id} to cart {cart_id}")
        with httpx.Client() as client:
            add_item_response = client.post(
                f"{MEALME_BASE_URL}/cart/{cart_id}/item",
                json={"product_id": product_id, "quantity": quantity},
                headers=headers,
                timeout=30.0,
            )
            add_item_response.raise_for_status()
            logger.info("Item added to cart successfully")

        # Step 5: Create order
        logger.info("Creating order")
        # Prepare customer address from params
        customer_address = customer.get("address", {})
        if not customer_address and address:
            # If address is a string, try to parse it or use it as street_address
            customer_address = {"street_address": address}

        order_payload = {
            "location_id": location_id,
            "fulfillment_method": "Delivery",
            "customer": {
                "name": customer.get("name", ""),
                "email": customer.get("email", ""),
                "address": customer_address,
                "phone_number": customer.get("phone_number", ""),
            },
            "items": [{"product_id": product_id, "quantity": quantity}],
        }

        if dropoff_instructions:
            order_payload["dropoff_instructions"] = dropoff_instructions

        with httpx.Client() as client:
            order_response = client.post(
                f"{MEALME_BASE_URL}/order",
                json=order_payload,
                headers=headers,
                timeout=30.0,
            )
            order_response.raise_for_status()
            order_data = order_response.json()
            order_id = order_data["id"]
            logger.info(f"Created order: {order_id}")

        # Step 6: Get checkout link
        logger.info(f"Retrieving payment link for order {order_id}")
        with httpx.Client() as client:
            payment_link_response = client.get(
                f"{MEALME_BASE_URL}/order/{order_id}/payment-link",
                headers=headers,
                timeout=30.0,
            )
            payment_link_response.raise_for_status()
            payment_link_data = payment_link_response.json()
            checkout_url = payment_link_data.get("url", "")

            if not checkout_url:
                return {
                    "status": "error",
                    "error": "Payment link not found in response",
                }

            logger.info("Order workflow completed successfully")

            # Return success response
            return {
                "status": "success",
                "order_id": order_id,
                "product": product_name,
                "checkout_url": checkout_url,
            }

    except httpx.HTTPStatusError as e:
        error_msg = f"HTTP error {e.response.status_code}: {e.response.text}"
        logger.error(error_msg)
        return {"status": "error", "error": error_msg}

    except httpx.RequestError as e:
        error_msg = f"Request error: {str(e)}"
        logger.error(error_msg)
        return {"status": "error", "error": error_msg}

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return {"status": "error", "error": error_msg}


class OrderFoodWorkflow:
    """
    Order Food Workflow class implementing the Workflow protocol.

    This workflow orchestrates the complete food ordering process through the MealMe API.
    It accepts a JSON message string containing order parameters and executes the workflow.
    """

    name = "order_food"
    description = "Order food through MealMe API - searches products, creates cart, places order, and retrieves checkout link"

    def execute(
        self, message: str, user_id: str | None = None, channel_id: str | None = None
    ) -> dict[str, Any]:
        """
        Execute the order_food workflow.

        The message should be a JSON string containing:
        - query: Product search term (e.g., "coffee", "Cold Brew")
        - address: Delivery address (optional if latitude/longitude provided)
        - latitude: Latitude coordinate (optional if address provided)
        - longitude: Longitude coordinate (optional if address provided)
        - customer: Customer information dict with name, email, phone_number, and address
        - dropoff_instructions: Optional delivery instructions
        - quantity: Quantity of product to order (default: 1)

        Args:
            message: JSON string containing workflow parameters
            user_id: Optional user identifier (not used in this workflow)
            channel_id: Optional channel identifier (not used in this workflow)

        Returns:
            Dictionary with status, order_id, product name, and checkout_url
        """
        import json  # Import only where needed (in this method)

        try:
            # Parse JSON message to extract parameters
            params = json.loads(message)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON message: {e}")
            return {
                "status": "error",
                "error": f"Invalid JSON in message: {str(e)}",
            }

        # Call the run function with parsed parameters
        return run(params)
