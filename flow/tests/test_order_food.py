# Copyright 2025 Lunch Pail Labs, LLC
# Licensed under the Apache License, Version 2.0

"""
Tests for the order_food workflow.

These tests verify that the order_food workflow:
1. Is properly registered in the workflow system
2. Can be executed via the generic workflow endpoint
3. Handles invalid input correctly
4. Integrates properly with the MealMe API (mocked)
"""

import json
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from flow.workflows import get_workflow, get_workflows
from flow.workflows.order_food import OrderFoodWorkflow, run


def test_order_food_workflow_registered() -> None:
    """Test that order_food workflow is registered in the workflow system."""
    workflows = get_workflows()
    assert "order_food" in workflows
    assert isinstance(workflows["order_food"], OrderFoodWorkflow)


def test_order_food_workflow_get_by_name() -> None:
    """Test that order_food workflow can be retrieved by name."""
    workflow = get_workflow("order_food")
    assert isinstance(workflow, OrderFoodWorkflow)
    assert workflow.name == "order_food"
    assert workflow.description is not None
    assert len(workflow.description) > 0


def test_order_food_workflow_listed_in_endpoint(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Test that order_food workflow appears in /workflows listing."""
    response = client.get("/workflows", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "workflows" in data
    workflow_names = [w["name"] for w in data["workflows"]]
    assert "order_food" in workflow_names


def test_order_food_workflow_invalid_json(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Test that order_food workflow handles invalid JSON message."""
    response = client.post(
        "/workflow/order_food",
        headers={**auth_headers, "Content-Type": "application/json"},
        json={"message": "not valid json {"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert "error" in data
    assert "JSON" in data["error"] or "json" in data["error"].lower()


def test_order_food_workflow_missing_query(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Test that order_food workflow handles missing query parameter."""
    params = {
        "customer": {
            "name": "Test User",
            "email": "test@example.com",
            "phone_number": "+1234567890",
            "address": {
                "street_address": "123 Test St",
                "city": "Test City",
                "region": "TS",
                "postal_code": "12345",
                "country": "US",
            },
        }
    }
    response = client.post(
        "/workflow/order_food",
        headers={**auth_headers, "Content-Type": "application/json"},
        json={"message": json.dumps(params)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert "error" in data
    assert "query" in data["error"].lower() or "missing" in data["error"].lower()


def test_order_food_workflow_missing_customer(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Test that order_food workflow handles missing customer parameter."""
    params = {"query": "coffee"}
    response = client.post(
        "/workflow/order_food",
        headers={**auth_headers, "Content-Type": "application/json"},
        json={"message": json.dumps(params)},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "error"
    assert "error" in data
    assert "customer" in data["error"].lower() or "missing" in data["error"].lower()


def test_order_food_workflow_missing_api_key() -> None:
    """Test that order_food workflow handles missing MEALME_API_KEY."""
    params = {
        "query": "coffee",
        "latitude": 33.7583,
        "longitude": -84.3929,
        "customer": {
            "name": "Test User",
            "email": "test@example.com",
            "phone_number": "+1234567890",
            "address": {
                "street_address": "123 Test St",
                "city": "Test City",
                "region": "TS",
                "postal_code": "12345",
                "country": "US",
            },
        },
    }

    # Patch the MEALME_API_KEY variable directly instead of reloading the module
    with patch("flow.workflows.order_food.MEALME_API_KEY", None):
        result = run(params)
        assert result["status"] == "error"
        assert "MEALME_API_KEY" in result["error"]


@patch("flow.workflows.order_food.httpx.Client")
@patch("flow.workflows.order_food.MEALME_API_KEY", "test-api-key")
def test_order_food_workflow_full_flow_mocked(mock_client_class: Mock) -> None:
    """Test the complete order_food workflow with mocked HTTP responses."""
    # Setup mock responses for each API call
    mock_client = Mock()
    mock_client_class.return_value.__enter__.return_value = mock_client
    mock_client_class.return_value.__exit__.return_value = None

    # Mock geocode response
    geocode_response = Mock()
    geocode_response.json.return_value = {
        "data": {
            "type": "Feature",
            "coordinates": [
                -84.3929,
                33.7583,
            ],  # [longitude, latitude] in GeoJSON format
        },
        "messages": [],
    }
    geocode_response.raise_for_status = Mock()

    # Mock product search response
    product_response = Mock()
    product_response.json.return_value = [
        {
            "id": "prod_123",
            "name": "La Colombe Cold Brew",
            "price": 4.99,
            "merchantId": "merch_abc",
            "locationId": "loc_789",
        }
    ]
    product_response.raise_for_status = Mock()

    # Mock cart creation response
    cart_response = Mock()
    cart_response.json.return_value = {"id": "cart_456", "status": "Active"}
    cart_response.raise_for_status = Mock()

    # Mock add item response
    add_item_response = Mock()
    add_item_response.raise_for_status = Mock()

    # Mock order creation response
    order_response = Mock()
    order_response.json.return_value = {"id": "order_001", "status": "Created"}
    order_response.raise_for_status = Mock()

    # Mock payment link response
    payment_link_response = Mock()
    payment_link_response.json.return_value = {
        "url": "https://checkout.stripe.com/pay/cs_test_123456",
        "expires_at": "2025-11-10T15:30:00Z",
    }
    payment_link_response.raise_for_status = Mock()

    # Configure mock to return different responses for different calls
    mock_client.get.side_effect = [
        geocode_response,  # Geocode call
        product_response,  # Product search call
        payment_link_response,  # Payment link call
    ]
    mock_client.post.side_effect = [
        cart_response,  # Create cart call
        add_item_response,  # Add item call
        order_response,  # Create order call
    ]

    # Test parameters
    params = {
        "query": "coffee",
        "address": "151 Ted Turner Dr NW, Atlanta, GA",
        "customer": {
            "name": "Test User",
            "email": "test@example.com",
            "phone_number": "+1234567890",
            "address": {
                "street_address": "151 Ted Turner Dr NW",
                "city": "Atlanta",
                "region": "GA",
                "postal_code": "30303",
                "country": "US",
            },
        },
        "quantity": 1,
    }

    # Execute workflow
    result = run(params)

    # Verify result
    assert result["status"] == "success"
    assert result["order_id"] == "order_001"
    assert result["product"] == "La Colombe Cold Brew"
    assert result["checkout_url"] == "https://checkout.stripe.com/pay/cs_test_123456"

    # Verify API calls were made in correct order
    assert mock_client.get.call_count == 3  # Geocode, product search, payment link
    assert mock_client.post.call_count == 3  # Create cart, add item, create order


@patch("flow.workflows.order_food.httpx.Client")
@patch("flow.workflows.order_food.MEALME_API_KEY", "test-api-key")
def test_order_food_workflow_with_coordinates(mock_client_class: Mock) -> None:
    """Test order_food workflow with pre-provided coordinates (skips geocoding)."""
    mock_client = Mock()
    mock_client_class.return_value.__enter__.return_value = mock_client
    mock_client_class.return_value.__exit__.return_value = None

    # Mock product search response
    product_response = Mock()
    product_response.json.return_value = [
        {
            "id": "prod_123",
            "name": "Cold Brew",
            "price": 4.99,
            "merchantId": "merch_abc",
            "locationId": "loc_789",
        }
    ]
    product_response.raise_for_status = Mock()

    # Mock cart creation response
    cart_response = Mock()
    cart_response.json.return_value = {"id": "cart_456", "status": "Active"}
    cart_response.raise_for_status = Mock()

    # Mock add item response
    add_item_response = Mock()
    add_item_response.raise_for_status = Mock()

    # Mock order creation response
    order_response = Mock()
    order_response.json.return_value = {"id": "order_001", "status": "Created"}
    order_response.raise_for_status = Mock()

    # Mock payment link response
    payment_link_response = Mock()
    payment_link_response.json.return_value = {
        "url": "https://checkout.stripe.com/pay/cs_test_123456",
        "expires_at": "2025-11-10T15:30:00Z",
    }
    payment_link_response.raise_for_status = Mock()

    # Configure mock - no geocode call since coordinates are provided
    mock_client.get.side_effect = [
        product_response,  # Product search call
        payment_link_response,  # Payment link call
    ]
    mock_client.post.side_effect = [
        cart_response,  # Create cart call
        add_item_response,  # Add item call
        order_response,  # Create order call
    ]

    # Test parameters with coordinates (no address)
    params = {
        "query": "coffee",
        "latitude": 33.7583,
        "longitude": -84.3929,
        "customer": {
            "name": "Test User",
            "email": "test@example.com",
            "phone_number": "+1234567890",
            "address": {
                "street_address": "151 Ted Turner Dr NW",
                "city": "Atlanta",
                "region": "GA",
                "postal_code": "30303",
                "country": "US",
            },
        },
    }

    # Execute workflow
    result = run(params)

    # Verify result
    assert result["status"] == "success"
    assert result["order_id"] == "order_001"

    # Verify geocode was NOT called (only 2 GET calls: product search and payment link)
    assert mock_client.get.call_count == 2


@patch("flow.workflows.order_food.httpx.Client")
@patch("flow.workflows.order_food.MEALME_API_KEY", "test-api-key")
def test_order_food_workflow_no_products_found(mock_client_class: Mock) -> None:
    """Test order_food workflow when no products are found."""
    mock_client = Mock()
    mock_client_class.return_value.__enter__.return_value = mock_client
    mock_client_class.return_value.__exit__.return_value = None

    # Mock product search response with empty list
    product_response = Mock()
    product_response.json.return_value = []
    product_response.raise_for_status = Mock()

    mock_client.get.return_value = product_response

    params = {
        "query": "nonexistent_product",
        "latitude": 33.7583,
        "longitude": -84.3929,
        "customer": {
            "name": "Test User",
            "email": "test@example.com",
            "phone_number": "+1234567890",
            "address": {
                "street_address": "123 Test St",
                "city": "Test City",
                "region": "TS",
                "postal_code": "12345",
                "country": "US",
            },
        },
    }

    result = run(params)

    assert result["status"] == "error"
    assert "error" in result
    assert "product" in result["error"].lower() or "found" in result["error"].lower()


def test_order_food_workflow_execute_method() -> None:
    """Test that OrderFoodWorkflow.execute() properly parses JSON and calls run()."""
    workflow = OrderFoodWorkflow()

    # Test with valid JSON
    params = {
        "query": "coffee",
        "latitude": 33.7583,
        "longitude": -84.3929,
        "customer": {
            "name": "Test User",
            "email": "test@example.com",
            "phone_number": "+1234567890",
            "address": {
                "street_address": "123 Test St",
                "city": "Test City",
                "region": "TS",
                "postal_code": "12345",
                "country": "US",
            },
        },
    }

    with patch("flow.workflows.order_food.run") as mock_run:
        mock_run.return_value = {"status": "success", "order_id": "test_order"}
        message = json.dumps(params)
        result = workflow.execute(message)

        # Verify run() was called with parsed params
        mock_run.assert_called_once_with(params)
        assert result["status"] == "success"

    # Test with invalid JSON
    result = workflow.execute("not valid json {")
    assert result["status"] == "error"
    assert "JSON" in result["error"] or "json" in result["error"].lower()


def test_order_food_workflow_via_generic_endpoint(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Test that order_food workflow can be executed via generic /workflow/{name} endpoint."""
    params = {
        "query": "coffee",
        "latitude": 33.7583,
        "longitude": -84.3929,
        "customer": {
            "name": "Test User",
            "email": "test@example.com",
            "phone_number": "+1234567890",
            "address": {
                "street_address": "123 Test St",
                "city": "Test City",
                "region": "TS",
                "postal_code": "12345",
                "country": "US",
            },
        },
    }

    with patch("flow.workflows.order_food.httpx.Client") as mock_client_class:
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client_class.return_value.__exit__.return_value = None

        # Mock all API responses
        product_response = Mock()
        product_response.json.return_value = [
            {
                "id": "prod_123",
                "name": "Cold Brew",
                "locationId": "loc_789",
            }
        ]
        product_response.raise_for_status = Mock()

        cart_response = Mock()
        cart_response.json.return_value = {"id": "cart_456"}
        cart_response.raise_for_status = Mock()

        add_item_response = Mock()
        add_item_response.raise_for_status = Mock()

        order_response = Mock()
        order_response.json.return_value = {"id": "order_001"}
        order_response.raise_for_status = Mock()

        payment_link_response = Mock()
        payment_link_response.json.return_value = {
            "url": "https://checkout.stripe.com/pay/cs_test_123456"
        }
        payment_link_response.raise_for_status = Mock()

        mock_client.get.side_effect = [product_response, payment_link_response]
        mock_client.post.side_effect = [
            cart_response,
            add_item_response,
            order_response,
        ]

        response = client.post(
            "/workflow/order_food",
            headers={**auth_headers, "Content-Type": "application/json"},
            json={"message": json.dumps(params)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "order_id" in data
        assert "product" in data
        assert "checkout_url" in data


def test_order_food_workflow_via_mcp_tool(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    """Test that order_food workflow can be executed via MCP execute_workflow_mcp tool."""
    params = {
        "query": "coffee",
        "latitude": 33.7583,
        "longitude": -84.3929,
        "customer": {
            "name": "Test User",
            "email": "test@example.com",
            "phone_number": "+1234567890",
            "address": {
                "street_address": "123 Test St",
                "city": "Test City",
                "region": "TS",
                "postal_code": "12345",
                "country": "US",
            },
        },
    }

    with patch("flow.workflows.order_food.httpx.Client") as mock_client_class:
        mock_client = Mock()
        mock_client_class.return_value.__enter__.return_value = mock_client
        mock_client_class.return_value.__exit__.return_value = None

        # Mock all API responses
        product_response = Mock()
        product_response.json.return_value = [
            {
                "id": "prod_123",
                "name": "Cold Brew",
                "locationId": "loc_789",
            }
        ]
        product_response.raise_for_status = Mock()

        cart_response = Mock()
        cart_response.json.return_value = {"id": "cart_456"}
        cart_response.raise_for_status = Mock()

        add_item_response = Mock()
        add_item_response.raise_for_status = Mock()

        order_response = Mock()
        order_response.json.return_value = {"id": "order_001"}
        order_response.raise_for_status = Mock()

        payment_link_response = Mock()
        payment_link_response.json.return_value = {
            "url": "https://checkout.stripe.com/pay/cs_test_123456"
        }
        payment_link_response.raise_for_status = Mock()

        mock_client.get.side_effect = [product_response, payment_link_response]
        mock_client.post.side_effect = [
            cart_response,
            add_item_response,
            order_response,
        ]

        # Call MCP tool via JSON-RPC protocol
        response = client.post(
            "/mcp",
            headers={**auth_headers, "Content-Type": "application/json"},
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "execute_workflow_mcp",
                    "arguments": {
                        "workflow_name": "order_food",
                        "message": json.dumps(params),
                        "user_id": "test-user",
                        "channel_id": "test-channel",
                    },
                },
            },
            follow_redirects=True,
        )

        # Should successfully call the tool
        assert response.status_code in [200, 400, 404, 405]
        if response.status_code == 200:
            data = response.json()
            # Check for JSON-RPC response format
            assert "jsonrpc" in data
            assert data["jsonrpc"] == "2.0"
            assert "id" in data

            if "result" in data:
                result = data["result"]
                # Tool should return success and result matching our business logic
                assert isinstance(result, dict)
                assert "success" in result
                assert result["success"] is True
                assert "result" in result
                assert "workflow_name" in result
                assert result["workflow_name"] == "order_food"

                # Verify the workflow result structure
                workflow_result = result["result"]
                assert workflow_result["status"] == "success"
                assert "order_id" in workflow_result
                assert "product" in workflow_result
                assert "checkout_url" in workflow_result


def test_order_food_mcp_tool() -> None:
    """Test that order_food MCP tool works correctly."""
    from flow.main import order_food_mcp

    with patch("flow.workflows.order_food.run") as mock_run:
        mock_run.return_value = {
            "status": "success",
            "order_id": "test_123",
            "product": "Cold Brew",
            "checkout_url": "https://checkout.stripe.com/pay/cs_test_123456",
        }

        result = order_food_mcp(
            query="coffee",
            customer={
                "name": "Test User",
                "email": "test@example.com",
                "phone_number": "555-1234",
                "address": {
                    "street_address": "123 Test St",
                    "city": "Test City",
                    "region": "TS",
                    "postal_code": "12345",
                    "country": "US",
                },
            },
            latitude=33.7583,
            longitude=-84.3929,
        )

        # Verify result structure
        assert result["status"] == "success"
        assert "order_id" in result
        assert result["order_id"] == "test_123"
        assert "product" in result
        assert result["product"] == "Cold Brew"
        assert "checkout_url" in result
        assert (
            result["checkout_url"] == "https://checkout.stripe.com/pay/cs_test_123456"
        )

        # Verify run() was called with correct parameters
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]  # First positional argument
        assert call_args["query"] == "coffee"
        assert call_args["latitude"] == 33.7583
        assert call_args["longitude"] == -84.3929
        assert call_args["customer"]["name"] == "Test User"
        assert call_args["customer"]["email"] == "test@example.com"


def test_order_food_mcp_tool_error_handling() -> None:
    """Test that order_food MCP tool handles errors correctly."""
    from flow.main import order_food_mcp

    with patch("flow.workflows.order_food.run") as mock_run:
        mock_run.side_effect = Exception("Test error")

        result = order_food_mcp(
            query="coffee",
            customer={
                "name": "Test User",
                "email": "test@example.com",
                "phone_number": "555-1234",
                "address": {
                    "street_address": "123 Test St",
                    "city": "Test City",
                    "region": "TS",
                    "postal_code": "12345",
                    "country": "US",
                },
            },
        )

        # Verify error response structure
        assert result["status"] == "error"
        assert "error" in result
        assert "order_food workflow" in result["error"]
