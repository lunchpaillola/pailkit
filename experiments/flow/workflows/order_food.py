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
        # First, determine fulfillment method preference (Delivery first, then Pickup)
        # We'll use this to filter products that support the desired fulfillment method
        preferred_fulfillment_method = "Delivery"  # Default preference

        # Check if a specific product_id was provided
        product_id_param = params.get("product_id")

        logger.info(f"Searching for products with query: {query}")
        with httpx.Client() as client:
            # Build search params
            search_params = {
                "latitude": latitude,
                "longitude": longitude,
            }

            # If product_id is provided, search by product ID (exact match)
            # Don't filter by fulfillmentMethod when searching by productId
            if product_id_param:
                search_params["productId"] = product_id_param
                logger.info(f"Searching for specific product ID: {product_id_param}")
            else:
                # Otherwise, search by query and filter by fulfillment method
                search_params["query"] = query
                search_params["fulfillmentMethod"] = [preferred_fulfillment_method]

            # Search with fulfillmentMethod filter to only get products that support Delivery
            product_response = client.get(
                f"{MEALME_BASE_URL}/product",
                params=search_params,
                headers=headers,
                timeout=30.0,
            )
            product_response.raise_for_status()
            product_data = product_response.json()

            # Handle different response formats
            # The API might return a list directly, or a dict with 'data' key
            if isinstance(product_data, dict):
                # Check if it's a dict with a 'data' or 'products' key containing a list
                products = product_data.get("data", product_data.get("products", []))
                # If still a dict, convert values to list
                if isinstance(products, dict):
                    products = list(products.values())
            elif isinstance(product_data, list):
                products = product_data
            else:
                logger.error(
                    f"Unexpected response format: {type(product_data)}, data: {product_data}"
                )
                return {
                    "status": "error",
                    "error": f"Unexpected response format from product API: {type(product_data)}",
                }

            if not products or len(products) == 0:
                logger.warning(f"No products found in response: {product_data}")
                if product_id_param:
                    return {
                        "status": "error",
                        "error": f"No products found for product_id: {product_id_param}",
                    }
                else:
                    return {
                        "status": "error",
                        "error": f"No products found for query: {query}",
                    }

            # Select the first product (already filtered by fulfillment method)
            selected_product = products[0]
            product_id = selected_product.get("id") or selected_product.get(
                "product_id"
            )
            product_name = selected_product.get("name", query)

            # Get fulfillment methods from the product (should include our preferred method)
            fulfillment_methods = selected_product.get("fulfillment_methods", [])

            # Try different possible field names for location ID
            # Check direct fields first
            location_id = selected_product.get("locationId") or selected_product.get(
                "location_id"
            )

            # If not found, check nested location object
            if not location_id:
                location_obj = selected_product.get("location") or selected_product.get(
                    "locationData"
                )
                if location_obj:
                    if isinstance(location_obj, dict):
                        location_id = (
                            location_obj.get("id")
                            or location_obj.get("locationId")
                            or location_obj.get("location_id")
                        )
                    elif isinstance(location_obj, str):
                        location_id = location_obj

            logger.info(f"Selected product: {product_name} (ID: {product_id})")
            logger.info(f"Product fulfillment methods: {fulfillment_methods}")
            logger.info(f"Product data: {selected_product}")
            logger.info(f"Extracted location_id: {location_id}")

            if not product_id:
                return {
                    "status": "error",
                    "error": f"Product missing ID field. Product data: {selected_product}",
                }

            if not location_id:
                return {
                    "status": "error",
                    "error": f"Product missing locationId. Product data: {selected_product}",
                }

        # Step 3: Create cart
        logger.info(f"Creating cart for location: {location_id}")
        # Get customer ID for user_id (use email or name as fallback)
        customer_id = (
            customer.get("id")
            or customer.get("email")
            or customer.get("name", "pailflow_user")
        )
        # Get fulfillment method from product (should already be filtered, but verify)
        fulfillment_methods = selected_product.get("fulfillment_methods", [])
        # Use preferred method if available, otherwise use first available
        if preferred_fulfillment_method in fulfillment_methods:
            fulfillment_method = preferred_fulfillment_method
        elif "Delivery" in fulfillment_methods:
            fulfillment_method = "Delivery"
        elif "Pickup" in fulfillment_methods:
            fulfillment_method = "Pickup"
        elif fulfillment_methods:
            fulfillment_method = fulfillment_methods[0]
        else:
            fulfillment_method = "Delivery"  # Default to Delivery
        logger.info(
            f"Using fulfillment method: {fulfillment_method} (available: {fulfillment_methods})"
        )

        with httpx.Client() as client:
            # Cart creation - include fulfillment_method to match product availability
            cart_payload = {
                "location_id": location_id,
                "user_id": customer_id,
                "status": "Active",
                "fulfillment_method": fulfillment_method,  # Set fulfillment method on cart
            }
            logger.info(f"Cart creation payload: {cart_payload}")
            cart_response = client.post(
                f"{MEALME_BASE_URL}/cart",
                json=cart_payload,
                headers=headers,
                timeout=30.0,
            )
            cart_response.raise_for_status()
            cart_data = cart_response.json()
            logger.info(f"Cart creation response: {cart_data}")

            # Handle different response formats
            if isinstance(cart_data, dict):
                # Try direct fields first
                cart_id = cart_data.get("id") or cart_data.get("cart_id")
                # If not found, check if 'data' field contains the ID (could be string or dict)
                if not cart_id:
                    data_field = cart_data.get("data")
                    if isinstance(data_field, str):
                        # If data is a string, it's the cart ID directly
                        cart_id = data_field
                    elif isinstance(data_field, dict):
                        # If data is a dict, get id from it
                        cart_id = data_field.get("id") or data_field.get("cart_id")
                # Check if cart response has location_id we should use for order
                cart_location_id = cart_data.get("location_id")
                if cart_location_id:
                    logger.info(
                        f"Using location_id from cart response: {cart_location_id}"
                    )
                    location_id = cart_location_id
                # Check if cart has a fulfillment_method set
                cart_fulfillment_method = cart_data.get("fulfillment_method")
                if cart_fulfillment_method:
                    logger.info(
                        f"Cart has fulfillment_method: {cart_fulfillment_method}"
                    )
                    fulfillment_method = cart_fulfillment_method
            elif isinstance(cart_data, list) and len(cart_data) > 0:
                # If response is a list, get the first item
                cart_id = (
                    cart_data[0].get("id") if isinstance(cart_data[0], dict) else None
                )
            else:
                cart_id = None

            if not cart_id:
                logger.error(f"Cart creation response missing ID: {cart_data}")
                return {
                    "status": "error",
                    "error": f"Cart creation failed: missing cart ID in response. Response: {cart_data}",
                }
            logger.info(f"Created cart: {cart_id}")

        # Step 4: Add item to cart
        logger.info(f"Adding product {product_id} ({product_name}) to cart {cart_id}")
        with httpx.Client() as client:
            # The API requires product_name (snake_case) in addition to product_id
            # Don't specify fulfillment_method here - let cart use its default
            add_item_payload = {
                "product_id": product_id,
                "product_name": product_name,
                "quantity": quantity,
            }
            logger.info(f"Add item payload: {add_item_payload}")
            add_item_response = client.post(
                f"{MEALME_BASE_URL}/cart/{cart_id}/item",
                json=add_item_payload,
                headers=headers,
                timeout=30.0,
            )
            logger.info(f"Add item response status: {add_item_response.status_code}")
            logger.info(f"Add item response: {add_item_response.text}")
            add_item_response.raise_for_status()

            # Get the item ID from the response (might be needed for order)
            add_item_data = add_item_response.json()
            cart_item_id = None
            if isinstance(add_item_data, dict):
                cart_item_id = (
                    add_item_data.get("data")
                    or add_item_data.get("id")
                    or add_item_data.get("item_id")
                )
            logger.info(f"Cart item ID: {cart_item_id}")
            logger.info("Item added to cart successfully")

        # Step 5: Create order
        logger.info("Creating order")
        # Prepare customer address from params
        customer_address = customer.get("address", {})
        if not customer_address and address:
            # If address is a string, try to parse it or use it as street_address
            customer_address = {"street_address": address}

        # Try to get location_id from cart if available, otherwise use product location_id
        # The cart might have a validated location_id we should use
        logger.info(f"Using location_id for order: {location_id}")

        # Order payload - API requires phone_number even though docs don't show it
        # Use product_id in items (not cart item_id)
        order_items = [{"product_id": product_id, "quantity": quantity}]

        order_payload = {
            "location_id": location_id,
            "fulfillment_method": fulfillment_method,
            "customer": {
                "id": customer_id,
                "name": customer.get("name", ""),
                "email": customer.get("email", ""),  # Include email in customer object
                "address": customer_address,
                "phone_number": customer.get("phone_number", ""),
            },
            "items": order_items,
            "tip": 5.0,  # Required field - set to $5 tip
        }

        logger.info(f"Order payload: {order_payload}")

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
            # Handle different response formats
            if isinstance(order_data, dict):
                order_id = order_data.get("id") or order_data.get("order_id")
            else:
                order_id = None

            if not order_id:
                logger.error(f"Order creation response missing ID: {order_data}")
                return {
                    "status": "error",
                    "error": "Order creation failed: missing order ID in response",
                }
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
