"""Tests for DatabaseService."""

from agent.configuration import Configuration
from services.database import DatabaseService


def test_database_service(config: Configuration) -> dict:
    """Test DatabaseService initialization and query methods.
    
    Args:
        config: Configuration object
        
    Returns:
        Dictionary with test results
    """
    result = {}
    
    try:
        database_service = DatabaseService(config)
        
        # Test 1: Initialize database (import all tables)
        result["initialize"] = {}
        try:
            init_results = database_service.initialize()
            result["initialize"]["status"] = "SUCCESS"
            result["initialize"]["results"] = init_results
            # Count successful imports
            success_count = sum(1 for r in init_results.values() if r.get("status") == "SUCCESS")
            result["initialize"]["tables_imported"] = success_count
            result["initialize"]["total_tables"] = len(init_results)
        except Exception as e:
            result["initialize"]["status"] = "ERROR"
            result["initialize"]["error"] = str(e)
            result["initialize"]["error_type"] = type(e).__name__
        
        # Test 2: Check table existence
        result["table_checks"] = {}
        tables_to_check = ['customers', 'orders', 'transactions', 'refunds', 'issues']
        for table_name in tables_to_check:
            try:
                exists = database_service.table_exists(table_name)
                table_info = database_service.get_table_info(table_name)
                result["table_checks"][table_name] = {
                    "exists": exists,
                    "row_count": table_info.get("row_count", 0),
                    "column_count": len(table_info.get("columns", []))
                }
            except Exception as e:
                result["table_checks"][table_name] = {
                    "exists": False,
                    "error": str(e)
                }
        
        # Test 3: Workflow query methods (find operations)
        result["find_operations"] = {}
        
        # Test 3a: Find order
        try:
            # Try to find a sample order (using a common order number pattern)
            test_order_no = "ORD00009997"  # From the Jira ticket we tested earlier
            order = database_service.find_order(test_order_no)
            if order:
                result["find_operations"]["find_order"] = {
                    "status": "SUCCESS",
                    "order_no": test_order_no,
                    "found": True,
                    "order_keys": list(order.keys())[:5]  # Show first 5 keys
                }
            else:
                result["find_operations"]["find_order"] = {
                    "status": "SUCCESS",
                    "order_no": test_order_no,
                    "found": False,
                    "note": "Order not found (may not exist in database)"
                }
        except Exception as e:
            result["find_operations"]["find_order"] = {
                "status": "ERROR",
                "error": str(e),
                "error_type": type(e).__name__
            }
        
        # Test 3b: Find transaction
        try:
            # Try to find a sample transaction
            test_transaction_id = "TXN001"  # Sample transaction ID
            transaction = database_service.find_transaction(test_transaction_id)
            if transaction:
                result["find_operations"]["find_transaction"] = {
                    "status": "SUCCESS",
                    "transaction_id": test_transaction_id,
                    "found": True,
                    "transaction_keys": list(transaction.keys())[:5]
                }
            else:
                result["find_operations"]["find_transaction"] = {
                    "status": "SUCCESS",
                    "transaction_id": test_transaction_id,
                    "found": False,
                    "note": "Transaction not found (may not exist in database)"
                }
        except Exception as e:
            result["find_operations"]["find_transaction"] = {
                "status": "ERROR",
                "error": str(e),
                "error_type": type(e).__name__
            }
        
        # Test 3c: Query method (general SQL query)
        try:
            # Query to get sample data from orders table
            query_results = database_service.query(
                "SELECT order_no, customer_id, order_date_time FROM orders LIMIT 3"
            )
            result["find_operations"]["query"] = {
                "status": "SUCCESS",
                "results_count": len(query_results),
                "sample_result": query_results[0] if query_results else None
            }
        except Exception as e:
            result["find_operations"]["query"] = {
                "status": "ERROR",
                "error": str(e),
                "error_type": type(e).__name__
            }
        
        # Test 3d: Find customer
        try:
            # Try to find a customer (if we have customer data)
            customer_results = database_service.query("SELECT customer_id, email FROM customers LIMIT 1")
            if customer_results:
                test_customer_id = customer_results[0].get("customer_id")
                customer = database_service.find_customer(customer_id=test_customer_id)
                if customer:
                    result["find_operations"]["find_customer"] = {
                        "status": "SUCCESS",
                        "customer_id": test_customer_id,
                        "found": True,
                        "customer_keys": list(customer.keys())[:5]
                    }
                else:
                    result["find_operations"]["find_customer"] = {
                        "status": "SUCCESS",
                        "found": False
                    }
            else:
                result["find_operations"]["find_customer"] = {
                    "status": "SKIPPED",
                    "reason": "No customers in database"
                }
        except Exception as e:
            result["find_operations"]["find_customer"] = {
                "status": "ERROR",
                "error": str(e),
                "error_type": type(e).__name__
            }
        
        # Test 3e: Find issue
        try:
            # Try to find an issue by issue number
            test_issue_no = "AS-4"  # From issues.json
            issue = database_service.find_issue(issue_no=test_issue_no)
            if issue:
                result["find_operations"]["find_issue"] = {
                    "status": "SUCCESS",
                    "issue_no": test_issue_no,
                    "found": True,
                    "issue_keys": list(issue.keys())[:5],
                    "issue_data": {
                        "issue_id": issue.get("issue_id"),
                        "customer_id": issue.get("customer_id"),
                        "order_no": issue.get("order_no"),
                        "is_triaged": issue.get("is_triaged")
                    }
                }
            else:
                result["find_operations"]["find_issue"] = {
                    "status": "SUCCESS",
                    "issue_no": test_issue_no,
                    "found": False,
                    "note": "Issue not found (may not exist in database)"
                }
        except Exception as e:
            result["find_operations"]["find_issue"] = {
                "status": "ERROR",
                "error": str(e),
                "error_type": type(e).__name__
            }
        
        result["overall_status"] = "SUCCESS"
        result["database_path"] = str(config.database_path)
        
    except Exception as e:
        result["overall_status"] = "ERROR"
        result["error"] = str(e)
        result["error_type"] = type(e).__name__
        result["hint"] = "Check database_path configuration and ensure data files exist"
    
    return result

